"""
IM会话管理器

功能：
1. 管理多账号的GoofishImClient实例（单例模式）
2. 根据account_id获取或创建IM客户端连接
3. 断开指定账号连接
4. 从数据库获取账号Cookie
5. 管理前端WebSocket客户端，将IM推送消息转发给前端
"""
import asyncio
import json
from typing import Any, Callable, Dict, List, Optional, Set

from loguru import logger
from sqlalchemy import select
from starlette.websockets import WebSocket

from common.db.session import async_session_maker
from common.models import XYAccount

from .im_client import GoofishImClient


class ImSessionManager:
    """IM会话管理器（单例），管理多账号的IM WebSocket客户端"""

    _instance: Optional["ImSessionManager"] = None

    def __init__(self):
        # account_id -> GoofishImClient
        self.clients: Dict[str, GoofishImClient] = {}
        self._lock = asyncio.Lock()
        # 前端 WebSocket 客户端: account_id -> Set[WebSocket]
        self._ws_clients: Dict[str, Set[WebSocket]] = {}

    @classmethod
    def get_instance(cls) -> "ImSessionManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = ImSessionManager()
        return cls._instance

    async def get_or_connect(self, account_id: str) -> GoofishImClient:
        """
        获取已连接的客户端，或新建连接

        Args:
            account_id: 账号ID

        Returns:
            已连接的GoofishImClient

        Raises:
            ValueError: 账号不存在或Cookie为空
            Exception: 连接失败
        """
        async with self._lock:
            # 已有连接且仍在线，直接返回
            if account_id in self.clients:
                client = self.clients[account_id]
                if client.is_connected:
                    return client
                # 已断开，清理后重建
                await client.disconnect()
                del self.clients[account_id]

            # 从数据库获取账号行 ID 和 Cookie，供滑块成功后精准持久化。
            account_context = await self._get_account_context(account_id)
            if not account_context:
                raise ValueError(f"账号Cookie为空: {account_id}")
            account_row_id, cookies_str = account_context

            # 创建并连接
            client = GoofishImClient(
                account_id,
                cookies_str,
                account_row_id=account_row_id,
            )
            success = await client.connect()
            if not success:
                raise Exception(f"IM连接失败: {account_id}")

            self.clients[account_id] = client
            # 连接成功后，如果有前端WS客户端在等待，挂载推送回调
            await self._setup_push_callback_after_connect(account_id, client)
            return client

    async def disconnect(self, account_id: str):
        """
        断开指定账号的IM连接

        Args:
            account_id: 账号ID
        """
        async with self._lock:
            client = self.clients.pop(account_id, None)
            if client:
                await client.disconnect()
                logger.info(f"【{account_id}】IM会话已断开并移除")

    async def disconnect_all(self):
        """断开所有连接"""
        async with self._lock:
            for account_id, client in list(self.clients.items()):
                try:
                    await client.disconnect()
                except Exception as e:
                    logger.warning(f"【{account_id}】断开连接异常: {e}")
            self.clients.clear()
            logger.info("所有IM会话已断开")

    def get_connected_account_ids(self) -> list:
        """获取所有已连接的账号ID列表"""
        return [
            aid for aid, client in self.clients.items()
            if client.is_connected
        ]

    # ==================== 前端 WebSocket 客户端管理 ====================

    async def register_ws_client(self, account_id: str, ws: WebSocket):
        """
        注册前端 WebSocket 客户端，同时在 IM 客户端上挂载推送回调

        Args:
            account_id: 账号ID
            ws: 前端 WebSocket 连接
        """
        if account_id not in self._ws_clients:
            self._ws_clients[account_id] = set()
        self._ws_clients[account_id].add(ws)
        logger.info(f"【{account_id}】前端WebSocket客户端已注册，当前连接数: {len(self._ws_clients[account_id])}")

        # 确保 IM 客户端上已挂载推送回调
        client = self.clients.get(account_id)
        if client and client.is_connected:
            self._ensure_push_callback(account_id, client)

    async def unregister_ws_client(self, account_id: str, ws: WebSocket):
        """
        注销前端 WebSocket 客户端

        Args:
            account_id: 账号ID
            ws: 前端 WebSocket 连接
        """
        clients = self._ws_clients.get(account_id)
        if clients:
            clients.discard(ws)
            if not clients:
                del self._ws_clients[account_id]
        logger.info(
            f"【{account_id}】前端WebSocket客户端已注销，"
            f"剩余连接数: {len(self._ws_clients.get(account_id, set()))}"
        )

    def _ensure_push_callback(self, account_id: str, client: GoofishImClient):
        """确保 IM 客户端上已挂载推送回调（避免重复注册）"""
        # 用属性标记是否已挂载
        if getattr(client, "_push_cb_registered", False):
            return

        async def _forward_to_frontend(parsed_msg: dict):
            """将解析后的推送消息转发给所有前端 WebSocket 客户端"""
            ws_set = self._ws_clients.get(account_id)
            if not ws_set:
                return
            payload = json.dumps(parsed_msg, ensure_ascii=False)
            dead: List[WebSocket] = []
            for ws in ws_set:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            # 清理已断开的连接
            for ws in dead:
                ws_set.discard(ws)
            if not ws_set and account_id in self._ws_clients:
                del self._ws_clients[account_id]

        client.add_push_callback(_forward_to_frontend)
        client._push_cb_registered = True
        logger.info(f"【{account_id}】IM推送回调已挂载")

    async def _setup_push_callback_after_connect(
        self, account_id: str, client: GoofishImClient
    ):
        """连接成功后，如果已有前端客户端在等待，立即挂载推送回调"""
        if account_id in self._ws_clients and self._ws_clients[account_id]:
            self._ensure_push_callback(account_id, client)

    async def _get_account_context(self, account_id: str) -> tuple[int, str] | None:
        """
        从数据库获取账号行 ID 和 Cookie。

        Args:
            account_id: 账号ID

        Returns:
            ``(账号行ID, Cookie字符串)``，账号不存在或 Cookie 为空时返回 ``None``。
        """
        try:
            async with async_session_maker() as db:
                result = await db.execute(
                    select(XYAccount).where(
                        XYAccount.account_id == account_id
                    )
                )
                account = result.scalar_one_or_none()

                if not account:
                    logger.error(
                        f"【{account_id}】数据库中未找到账号"
                    )
                    return None

                if not account.cookie:
                    logger.error(
                        f"【{account_id}】账号Cookie为空"
                    )
                    return None

                return int(account.id), account.cookie

        except Exception as e:
            logger.error(f"【{account_id}】获取账号Cookie失败: {e}")
            return None


def get_im_session_manager() -> ImSessionManager:
    """获取IM会话管理器单例的快捷方法"""
    return ImSessionManager.get_instance()
