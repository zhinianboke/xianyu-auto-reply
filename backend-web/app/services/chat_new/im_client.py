"""
闲鱼 IM 在线聊天客户端。

功能：管理连接，查询会话和聊天记录，发送及撤回消息。
令牌获取和协议收发分别由 im_token.py、im_transport.py 提供，保留原有客户端接口。
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

from common.utils.xianyu_official_accounts import ensure_xianyu_message_recipient
from common.utils.xianyu_utils import generate_device_id, generate_mid, generate_uuid, trans_cookies
from .im_token import (
    CAPTCHA_KEYWORDS as CAPTCHA_KEYWORDS,
    CAPTCHA_MAX_RETRY as CAPTCHA_MAX_RETRY,
    ImTokenMixin,
)
from .im_transport import (
    HEARTBEAT_INTERVAL as HEARTBEAT_INTERVAL,
    REQUEST_TIMEOUT as REQUEST_TIMEOUT,
    TOKEN_INVALID_LWP_CODES as TOKEN_INVALID_LWP_CODES,
    ImRequestRejected as ImRequestRejected,
    ImTransportMixin,
)

WS_URL = "wss://wss-goofish.dingtalk.com/"


class GoofishImClient(ImTokenMixin, ImTransportMixin):
    """闲鱼IM WebSocket客户端，用于获取会话列表和聊天记录"""

    def __init__(
        self,
        account_id: str,
        cookies_str: str,
        *,
        account_row_id: int | None = None,
    ):
        """
        初始化IM客户端

        Args:
            account_id: 账号ID（数据库account_id）
            cookies_str: Cookie字符串
            account_row_id: 账号数据库行 ID，供滑块成功后精准写回 Cookie
        """
        self.account_id = account_id
        self.account_row_id = account_row_id
        self.cookies_str = cookies_str
        self.cookies: Dict[str, str] = trans_cookies(cookies_str)
        self.myid: str = self.cookies.get("unb", "")
        self._last_token_cache_lookup_succeeded = True
        self.device_id: str = generate_device_id(self.myid)
        self.token: str = ""
        self._captcha_token_cache_saved = False

        # WebSocket相关
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected: bool = False
        self._registered: bool = False

        # 请求-响应配对
        self._pending: Dict[str, asyncio.Future] = {}
        # 连接代次 + 重连互斥：多个并发请求同时收到 400 时只重连一次，
        # 后到的请求发现代次已变化即直接复用新连接，不再重复断连
        self._conn_generation: int = 0
        self._reconnect_lock: asyncio.Lock = asyncio.Lock()
        # 后台任务
        self._recv_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

        # 推送消息回调列表（用于向前端 WebSocket 转发实时消息）
        self._push_callbacks: List = []

    # ==================== 连接管理 ====================

    async def connect(self) -> bool:
        """
        建立连接：获取Token -> 连接WebSocket -> 注册

        Returns:
            是否连接成功
        """
        try:
            # 1. 获取IM Token
            self.token = await self._get_im_token()
            if not self.token:
                logger.error(f"【{self.account_id}】获取IM Token失败")
                return False
            logger.info(f"【{self.account_id}】获取IM Token成功")

            # 2. 建立WebSocket连接
            headers = {
                "Cookie": self.cookies_str,
                "Host": "wss-goofish.dingtalk.com",
                "Connection": "Upgrade",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36"
                ),
                "Origin": "https://www.goofish.com",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            self._session = aiohttp.ClientSession()
            # 超时策略（应对 wss:// 网络抖动）：
            # - total=None:      WebSocket 是长连接，原 total=30 会强制 30 秒后断开整个会话
            # - connect=30:      TCP + SSL/TLS 握手 + 连接池等待的超时（关键！wss 的 TLS 握手由此覆盖）
            # - sock_connect=30: 仅 TCP 三次握手超时（不含 TLS，作为 connect 的兜底）
            # - sock_read=None:  持久 WebSocket 不应有读超时（消息间隔可能很长）
            # - heartbeat=30:    aiohttp 库自身 PING 帧间隔 30 秒（与应用层心跳互补）
            self._ws = await self._session.ws_connect(
                WS_URL,
                headers=headers,
                heartbeat=30,
                timeout=aiohttp.ClientTimeout(
                    total=None,
                    connect=30,
                    sock_connect=30,
                    sock_read=None,
                ),
            )
            self._connected = True
            logger.info(f"【{self.account_id}】WebSocket连接成功")

            # 3. 启动消息接收循环
            self._recv_task = asyncio.create_task(self._recv_loop())

            # 4. 注册
            await self._register()
            self._registered = True
            logger.info(f"【{self.account_id}】IM注册成功")

            # 5. 注册后冷却（防止立即请求触发IM流控 400600001）
            await asyncio.sleep(3)

            # 6. 启动心跳
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            return True

        except Exception as e:
            logger.error(f"【{self.account_id}】IM连接失败: {e}")
            await self.disconnect()
            return False

    async def disconnect(self):
        """断开连接，释放资源"""
        self._connected = False
        self._registered = False

        # 取消后台任务
        for task in [self._heartbeat_task, self._recv_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._heartbeat_task = None
        self._recv_task = None

        # 拒绝所有待处理请求
        for mid, future in self._pending.items():
            if not future.done():
                future.set_exception(Exception("连接已断开"))
        self._pending.clear()

        # 关闭WebSocket
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None

        # 关闭HTTP会话
        if self._session and not self._session.closed:
            try:
                await self._session.close()
            except Exception:
                pass
        self._session = None

        logger.info(f"【{self.account_id}】IM连接已断开")

    @property
    def is_connected(self) -> bool:
        """是否已连接并注册（含底层 ws 真实状态双重检查，避免标志位与实际连接不同步）"""
        return (
            self._connected
            and self._registered
            and self._ws is not None
            and not self._ws.closed
        )

    # ==================== 业务接口 ====================

    async def get_conversations(
        self, start_timestamp: Optional[int] = None, limit: int = 20
    ) -> Dict[str, Any]:
        """
        获取会话列表（含流控自动重试）

        Args:
            start_timestamp: 开始时间戳，首页传None(使用MAX_SAFE_INTEGER)，翻页传nextCursor
            limit: 每页数量

        Returns:
            包含 hasMore, nextCursor, userConvs 的字典
        """
        if start_timestamp is None:
            start_timestamp = 9007199254740991  # Number.MAX_SAFE_INTEGER

        max_retries = 3
        for attempt in range(max_retries):
            def _build():
                mid = generate_mid()
                return mid, {
                    "lwp": "/r/Conversation/listNewestPagination",
                    "headers": {"mid": mid},
                    "body": [start_timestamp, limit],
                }

            # code=400 时会先刷新 Token 重连再重试一次（查询幂等，可安全重试）
            response = await self._send_and_wait_with_retry(_build)
            body = response.get("body", {})

            # 检查是否被流控
            if isinstance(body, dict) and body.get("code") == "400600001":
                wait_sec = (attempt + 1) * 2
                logger.warning(
                    f"【{self.account_id}】会话列表被流控，"
                    f"{wait_sec}秒后重试（{attempt + 1}/{max_retries}）"
                )
                await asyncio.sleep(wait_sec)
                continue

            return body

        # 重试耗尽，返回最后一次结果
        return body

    async def get_messages(
        self,
        cid: str,
        start_timestamp: Optional[int] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        获取单个会话的聊天记录

        Args:
            cid: 会话ID（不含@goofish后缀）
            start_timestamp: 开始时间戳，首页传None，翻页传nextCursor
            limit: 每页数量

        Returns:
            包含 hasMore, nextCursor, userMessageModels 的字典
        """
        if start_timestamp is None:
            start_timestamp = 9007199254740991

        # 确保cid带@goofish后缀
        full_cid = cid if "@goofish" in cid else f"{cid}@goofish"

        def _build():
            mid = generate_mid()
            return mid, {
                "lwp": "/r/MessageManager/listUserMessages",
                "headers": {"mid": mid},
                "body": [full_cid, False, start_timestamp, limit, False],
            }

        # code=400 时会先刷新 Token 重连再重试一次（查询幂等，可安全重试）
        response = await self._send_and_wait_with_retry(_build)
        return response.get("body", {})

    async def send_text_message(
        self, cid: str, to_user_id: str, text: str
    ) -> Dict[str, Any]:
        """
        发送文本消息

        参照 XianYuApis-master/goofish_live.py 的 send_msg 实现

        Args:
            cid: 会话ID（不含@goofish后缀）
            to_user_id: 对方用户ID
            text: 消息文本

        Returns:
            IM服务器响应
        Raises:
            ValueError: 接收方是禁止发送消息的官方机器人。
        """
        ensure_xianyu_message_recipient(to_user_id)
        full_cid = cid if "@goofish" in cid else f"{cid}@goofish"
        full_to = to_user_id if "@goofish" in to_user_id else f"{to_user_id}@goofish"
        full_self = f"{self.myid}@goofish"

        # 构造文本消息 payload
        payload = {"contentType": 1, "text": {"text": text}}
        data_b64 = base64.b64encode(
            json.dumps(payload).encode("utf-8")
        ).decode("utf-8")

        mid = generate_mid()
        message_uuid = generate_uuid()
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": mid},
            "body": [
                {
                    "uuid": message_uuid,
                    "cid": full_cid,
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {"type": 1, "data": data_b64},
                    },
                    "redPointPolicy": 0,
                    "extension": {"extJson": "{}"},
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                    "mtags": {},
                    "msgReadStatusSetting": 1,
                },
                {"actualReceivers": [full_to, full_self]},
            ],
        }
        # 发送非幂等：code=400 时只刷新 Token 重连、不自动重发，避免重复发送同一条消息
        response = await self._send_and_wait_with_retry(
            lambda: (mid, msg), retry_after_reconnect=False
        )
        # IM 服务端对违规内容会返回带 reason 的 body（如 CSI_FORBID 安全拦截），
        # 此时虽然响应携带 body 不会在 _send_and_wait 抛错，但消息实际未送达，
        # 需在此识别为发送失败并抛出明文原因，供上层反馈给前端。
        self._raise_if_send_rejected(response)
        # 解析服务端返回的 messageId，供消息撤回功能使用
        body = response.get("body", {})
        message_id = ""
        if isinstance(body, dict):
            raw_message_id = body.get("messageId") or body.get("1")
            if isinstance(raw_message_id, dict):
                raw_message_id = raw_message_id.get("messageId") or raw_message_id.get("1")
            if isinstance(raw_message_id, str):
                message_id = raw_message_id
        return {"response": response, "messageId": message_id, "uuid": message_uuid}

    async def send_image_message(
        self,
        cid: str,
        to_user_id: str,
        image_url: str,
        width: int = 800,
        height: int = 600,
    ) -> Dict[str, Any]:
        """
        发送图片消息

        与 send_text_message 协议一致，仅消息体内容为 contentType=2 的图片结构。
        图片必须是已上传到闲鱼CDN的可访问URL（通过 ImageUploader 上传得到）。

        Args:
            cid: 会话ID（不含@goofish后缀）
            to_user_id: 对方用户ID
            image_url: 闲鱼CDN图片URL
            width: 图片宽度（像素），用于前端按比例渲染
            height: 图片高度（像素）

        Returns:
            包含 response、messageId、uuid 的结果字典
        Raises:
            ValueError: 接收方是禁止发送消息的官方机器人。
        """
        ensure_xianyu_message_recipient(to_user_id)
        full_cid = cid if "@goofish" in cid else f"{cid}@goofish"
        full_to = to_user_id if "@goofish" in to_user_id else f"{to_user_id}@goofish"
        full_self = f"{self.myid}@goofish"

        # 构造图片消息 payload（pics 数组格式，与官方协议一致）
        payload = {
            "contentType": 2,
            "image": {
                "pics": [
                    {
                        "height": int(height),
                        "type": 0,
                        "url": image_url,
                        "width": int(width),
                    }
                ]
            },
        }
        data_b64 = base64.b64encode(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        ).decode("utf-8")

        mid = generate_mid()
        message_uuid = generate_uuid()
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": mid},
            "body": [
                {
                    "uuid": message_uuid,
                    "cid": full_cid,
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {"type": 1, "data": data_b64},
                    },
                    "redPointPolicy": 0,
                    "extension": {"extJson": "{}"},
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                    "mtags": {},
                    "msgReadStatusSetting": 1,
                },
                {"actualReceivers": [full_to, full_self]},
            ],
        }
        response = await self._send_and_wait_with_retry(
            lambda: (mid, msg), retry_after_reconnect=False
        )
        # 与文本发送一致，识别安全拦截等业务错误并抛出明文原因
        self._raise_if_send_rejected(response)
        body = response.get("body", {})
        message_id = ""
        if isinstance(body, dict):
            raw_message_id = body.get("messageId") or body.get("1")
            if isinstance(raw_message_id, dict):
                raw_message_id = raw_message_id.get("messageId") or raw_message_id.get("1")
            if isinstance(raw_message_id, str):
                message_id = raw_message_id
        return {"response": response, "messageId": message_id, "uuid": message_uuid}

    async def recall_message(self, message_id: str) -> Dict[str, Any]:
        """通过闲鱼官方 IM 协议撤回一条消息"""
        mid = generate_mid()
        # 撤回同样按非幂等处理：code=400 只重连不自动重发，由用户再点一次撤回
        response = await self._send_and_wait_with_retry(
            lambda: (mid, {
                "lwp": "/r/MessageManager/recallMessage",
                "headers": {"mid": mid},
                "body": [message_id],
            }),
            retry_after_reconnect=False,
        )
        if response.get("code") != 200:
            body = response.get("body", {})
            reason = body.get("reason") if isinstance(body, dict) else ""
            raise RuntimeError(reason or "闲鱼未确认撤回成功")
        return response

    @staticmethod
    def _raise_if_send_rejected(response: Dict[str, Any]) -> None:
        """检查发送响应是否被 IM 服务端拒绝（如安全拦截），是则抛出明文原因

        Args:
            response: IM 服务器返回的完整响应

        Raises:
            Exception: 当响应 body 含 reason（业务错误）时抛出，message 为服务端原因文案
        """
        if not isinstance(response, dict):
            return
        body = response.get("body", {})
        if isinstance(body, dict) and body.get("reason"):
            reason = body.get("reason", "")
            more_info = body.get("moreInfo", "")
            # moreInfo 形如 "CSI_FORBID||安全拦截"，附在原因后便于定位拦截类型
            detail = f"{reason}（{more_info}）" if more_info else reason
            raise Exception(detail)
