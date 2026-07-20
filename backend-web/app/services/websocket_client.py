"""
WebSocket 服务客户端

功能：
1. 封装对 WebSocket 服务的 HTTP 调用
2. 提供账号任务管理接口（启动、停止、重启、查询状态）
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import aiohttp

from app.core.config import get_settings
from app.core.http_client import get_http_client
from common.services.captcha.remote_timeout import get_remote_solve_timeout

logger = logging.getLogger(__name__)
settings = get_settings()


class WebSocketServiceClient:
    """WebSocket 服务客户端"""

    def __init__(self):
        self.base_url = settings.websocket_service_url.rstrip('/')
        self.http_client = get_http_client()

    async def start_account(self, account_id: str, cookie_value: str = None, user_id: int = None) -> dict:
        """启动账号任务
        
        Args:
            account_id: 账号ID
            cookie_value: Cookie值(可选，不传则从数据库获取)
            user_id: 用户ID(可选)
            
        Returns:
            响应数据
        """
        url = f"{self.base_url}/internal/accounts/{account_id}/start"
        try:
            data = {}
            if cookie_value:
                data["cookie_value"] = cookie_value
            if user_id:
                data["user_id"] = user_id
            response = await self.http_client.post(url, json=data if data else {})
            return response
        except Exception as e:
            logger.error(f"启动账号任务失败: {account_id}, 错误: {e}")
            return {"success": False, "message": f"启动账号任务失败: {str(e)}"}

    async def stop_account(self, account_id: str) -> dict:
        """停止账号任务
        
        Args:
            account_id: 账号ID
            
        Returns:
            响应数据
        """
        url = f"{self.base_url}/internal/accounts/{account_id}/stop"
        try:
            response = await self.http_client.post(url)
            return response
        except Exception as e:
            logger.error(f"停止账号任务失败: {account_id}, 错误: {e}")
            return {"success": False, "message": f"停止账号任务失败: {str(e)}"}

    async def restart_account(self, account_id: str) -> dict:
        """重启账号任务
        
        Args:
            account_id: 账号ID
            
        Returns:
            响应数据
        """
        url = f"{self.base_url}/internal/accounts/{account_id}/restart"
        try:
            response = await self.http_client.post(url, json={})
            return response
        except Exception as e:
            logger.error(f"重启账号任务失败: {account_id}, 错误: {e}")
            return {"success": False, "message": f"重启账号任务失败: {str(e)}"}

    async def get_account_status(self, account_id: str) -> dict:
        """查询账号任务状态
        
        Args:
            account_id: 账号ID
            
        Returns:
            响应数据
        """
        url = f"{self.base_url}/internal/accounts/{account_id}/status"
        try:
            response = await self.http_client.get(url)
            return response
        except Exception as e:
            logger.error(f"查询账号任务状态失败: {account_id}, 错误: {e}")
            return {"success": False, "message": f"查询账号任务状态失败: {str(e)}"}

    async def send_message(self, account_id: str, chat_id: str, content: str, message_type: str = "text") -> dict:
        """发送消息
        
        Args:
            account_id: 账号ID
            chat_id: 聊天ID
            content: 消息内容
            message_type: 消息类型（text/image）
            
        Returns:
            响应数据
        """
        url = f"{self.base_url}/internal/accounts/{account_id}/send-message"
        try:
            response = await self.http_client.post(url, json={
                "chat_id": chat_id,
                "content": content,
                "message_type": message_type
            })
            return response
        except Exception as e:
            logger.error(f"发送消息失败: {account_id}, 错误: {e}")
            return {"success": False, "message": f"发送消息失败: {str(e)}"}

    async def create_chat(
        self,
        account_id: str,
        buyer_id: str,
        item_id: str,
    ) -> dict:
        """创建（或获取）单聊会话
        
        调用 WebSocket 服务的内部API，通过账号的 WebSocket 连接向闲鱼发起
        /r/SingleChatConversation/create 请求，拿到 chat_id。
        
        服务端按 (pairFirst, pairSecond, bizType) 幂等生成 cid，
        已存在的会话直接返回现有 cid，不会重复创建。
        
        Args:
            account_id: 账号ID
            buyer_id: 买家用户ID（对方，不带 @goofish 后缀）
            item_id: 关联商品ID
        
        Returns:
            响应数据，成功时 data.chat_id 为会话ID
        """
        url = f"{self.base_url}/internal/accounts/{account_id}/create-chat"
        try:
            response = await self.http_client.post(url, json={
                "buyer_id": buyer_id,
                "item_id": item_id,
            })
            return response
        except Exception as e:
            logger.error(f"创建会话失败: account_id={account_id}, buyer_id={buyer_id}, 错误: {e}")
            return {"success": False, "message": f"创建会话失败: {str(e)}"}

    async def deliver_order(
        self,
        account_id: str,
        order_no: str,
        item_id: str,
        buyer_id: str,
        chat_id: str,
        card_id: int,
        is_bargain: bool = False,
        delivery_method: str = "manual",
        quantity: int = 1,
    ) -> dict:
        """订单发货
        
        调用WebSocket服务的内部API进行订单发货
        
        Args:
            account_id: 账号ID
            order_no: 订单号
            item_id: 商品ID
            buyer_id: 买家ID
            chat_id: 聊天ID
            card_id: 卡券ID
            is_bargain: 是否小刀订单
            delivery_method: 发货方式（manual-手动发货，scheduled-定时补发货，auto-自动发货）
            quantity: 订单数量，>1 时 internal API 会循环获取并发送 N 张卡券
                      （与自动发货 multi_quantity_delivery 行为对齐）
            
        Returns:
            响应数据
        """
        url = f"{self.base_url}/internal/orders/deliver"
        try:
            response = await self.http_client.post(url, json={
                "account_id": account_id,
                "order_no": order_no,
                "item_id": item_id,
                "buyer_id": buyer_id,
                "chat_id": chat_id,
                "card_id": card_id,
                "is_bargain": is_bargain,
                "delivery_method": delivery_method,
                "quantity": int(quantity) if quantity and quantity > 0 else 1,
            })
            return response
        except Exception as e:
            logger.error(f"订单发货失败: {order_no}, 错误: {e}")
            return {"success": False, "message": f"订单发货失败: {str(e)}"}


    async def confirm_no_logistics(
        self,
        account_id: str,
        order_no: str,
        item_id: str,
        buyer_id: str,
        is_bargain: bool = False,
    ) -> dict:
        """无物流发货：在闲鱼确认发货但不发送卡券内容"""
        url = f"{self.base_url}/internal/orders/confirm-no-logistics"
        try:
            return await self.http_client.post(url, json={
                "account_id": account_id,
                "order_no": order_no,
                "item_id": item_id,
                "buyer_id": buyer_id,
                "is_bargain": is_bargain,
            })
        except Exception as e:
            logger.error(f"无物流发货失败: {order_no}, 错误: {e}")
            return {"success": False, "message": f"无物流发货失败: {str(e)}"}

    async def cancel_order(self, account_id: str, order_no: str) -> dict:
        """卖家关闭（取消）一笔闲鱼订单"""
        try:
            return await self.http_client.post(
                f"{self.base_url}/internal/orders/cancel",
                json={"account_id": account_id, "order_no": order_no},
            )
        except Exception as e:
            logger.error(f"取消订单失败: {order_no}, 错误: {e}")
            return {"success": False, "message": f"取消订单失败: {str(e)}"}


    async def solve_captcha(self, account_id: str, url: str, browser_timeout: int = 40,
                            call_type: str = "remote", call_user: str | None = None,
                            cookies: str = "", device_id: str = "",
                            extended_queue_timeout: bool = False,
                            precreated_log_id: int | None = None,
                            account_row_id: int | None = None,
                            token_user_id: str = "",
                            persist_token_cache: bool = False,
                            token_cache_write_mode: str = "renewal") -> dict:
        """调用 websocket 服务独立过滑块（模式B：仅凭 punish 链接求解）。

        注意：过滑块（含重试/看门狗）耗时可能达数十秒，远超共享 http_client 的 30s 超时，
        故此处使用独立的 aiohttp 会话并放宽超时，避免 backend 端提前超时。

        Args:
            account_id: 外部账号标识（仅用于日志/浏览器实例隔离）
            url: punish 验证链接
            browser_timeout: 单次浏览器超时（秒）
            call_type: 调用类型（local/remote），用于风控日志
            call_user: 调用用户名（远程调用按秘钥查到），用于风控日志
            cookies: 可选账号 Cookie（调用方开启"传递Cookie"开关时传入），链接过期时凭此重取新链接
            device_id: 可选设备 ID，配合 cookies 重新请求 token 接口使用
            extended_queue_timeout: 是否为真人鼠标远程接口预留串行排队时间；默认关闭，
                避免改变 login、聊天等现有调用的失败等待时间
            precreated_log_id: backend-web 在 Redis 准入锁内预先创建的风控日志 ID
            account_row_id: 可选账号数据库行 ID，供 WebSocket 端成功后写回 Cookie
            token_user_id: 可选 Token 缓存用户 ID
            persist_token_cache: 是否由 WebSocket 端在成功后写入 Token 缓存
            token_cache_write_mode: Token 缓存写入模式，renewal 或 upsert

        Returns:
            websocket 返回的响应字典（success / data.engine / data.cookies）
        """
        endpoint = f"{self.base_url}/internal/captcha/solve"
        request_not_sent_errors = (aiohttp.ClientConnectorError, aiohttp.InvalidURL)
        connection_timeout_error = getattr(aiohttp, "ConnectionTimeoutError", None)
        if connection_timeout_error is not None:
            request_not_sent_errors += (connection_timeout_error,)
        total_timeout = (
            get_remote_solve_timeout(browser_timeout)
            if extended_queue_timeout
            else max(90, int(browser_timeout) + 60)
        )
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=total_timeout, connect=10)
            ) as session:
                payload = {
                    "account_id": account_id,
                    "url": url,
                    "browser_timeout": int(browser_timeout),
                    "call_type": call_type,
                    "call_user": call_user,
                    "cookies": cookies or "",
                    "device_id": device_id or "",
                    "risk_log_id": precreated_log_id,
                }
                if account_row_id is not None:
                    payload["account_row_id"] = int(account_row_id)
                if persist_token_cache:
                    payload["persist_token_cache"] = True
                    payload["token_user_id"] = token_user_id or ""
                    payload["token_cache_write_mode"] = token_cache_write_mode or "renewal"
                async with session.post(endpoint, json=payload) as resp:
                    return await resp.json(content_type=None)
        except request_not_sent_errors as e:
            logger.error(f"无法连接过滑块服务: account_id={account_id}, 错误: {e}")
            return {
                "success": False,
                "message": f"无法连接过滑块服务: {str(e)}",
                "_request_not_sent": True,
            }
        except asyncio.TimeoutError:
            logger.error(
                f"过滑块服务等待超时: account_id={account_id}, "
                f"总超时={total_timeout:.0f}秒"
            )
            return {
                "success": False,
                "message": f"过滑块服务等待超时（{total_timeout:.0f}秒）",
                "_request_status_unknown": True,
            }
        except Exception as e:
            logger.error(f"过滑块失败: account_id={account_id}, 错误: {e}")
            return {
                "success": False,
                "message": f"过滑块失败: {str(e)}",
                "_request_status_unknown": True,
            }


# 全局客户端实例
websocket_client = WebSocketServiceClient()
