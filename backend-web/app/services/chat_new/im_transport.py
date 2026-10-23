"""
在线聊天 IM 协议收发。

功能：注册连接、匹配请求响应、处理重连、推送消息及心跳。
由 GoofishImClient 继承，所有后台任务仍由客户端连接生命周期管理。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import aiohttp
from loguru import logger

from common.utils.xianyu_utils import generate_mid
from .push_message_parser import PushMessageParser

REQUEST_TIMEOUT = 20
HEARTBEAT_INTERVAL = 15
# Token/注册状态失效时，服务器返回无 body 的 400 响应。
TOKEN_INVALID_LWP_CODES = (400,)


class ImRequestRejected(Exception):
    """IM LWP 请求被服务端拒绝（响应 code 非 200 且不带 body）

    携带服务端返回的 code，供上层区分「Token/连接失效(400)」与其它拒绝原因。
    继承 Exception，原有 `except Exception` 的调用方行为不变。
    """

    def __init__(self, message: str, code: Any):
        super().__init__(message)
        self.code = code


class ImTransportMixin:
    """供在线聊天客户端复用的 LWP 协议收发流程。"""

    async def _register(self):
        """发送注册消息 (/reg) 并等待服务器确认，然后发送 ackDiff"""
        # 发送 /reg 并等待响应
        reg_mid = generate_mid()
        reg_msg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": "444e9908a51d1cb236a27862abc769c9",
                "token": self.token,
                "ua": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36 "
                    "DingTalk(2.1.5) OS(Windows/10) "
                    "Browser(Chrome/146.0.0.0) DingWeb/2.1.5 "
                    "IMPaaS DingWeb/2.1.5"
                ),
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": reg_mid,
            },
        }

        try:
            reg_response = await self._send_and_wait(reg_mid, reg_msg, timeout=5)
            reg_code = reg_response.get("code", 0)
            logger.info(
                f"【{self.account_id}】注册响应: code={reg_code}, "
                f"body={json.dumps(reg_response.get('body', {}), ensure_ascii=False)[:200]}"
            )
            if reg_code != 200:
                logger.warning(f"【{self.account_id}】注册返回非200: {reg_code}")
        except Exception as e:
            logger.warning(f"【{self.account_id}】等待注册响应异常: {e}，继续尝试")

        # 发送 ackDiff
        current_time = int(time.time() * 1000)
        ack_mid = generate_mid()
        ack_msg = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": ack_mid},
            "body": [
                {
                    "pipeline": "sync",
                    "tooLong2Tag": "PNM,1",
                    "channel": "sync",
                    "topic": "sync",
                    "highPts": 0,
                    "pts": current_time * 1000,
                    "seq": 0,
                    "timestamp": current_time,
                }
            ],
        }
        await self._send_raw(ack_msg)

        # 等待同步完成
        await asyncio.sleep(1)

    async def _send_raw(self, msg: dict):
        """直接发送消息（不等待响应）"""
        if not self._ws or self._ws.closed:
            raise Exception("WebSocket未连接")
        await self._ws.send_json(msg)

    async def _send_and_wait(
        self, mid: str, msg: dict, timeout: float = REQUEST_TIMEOUT
    ) -> dict:
        """
        发送消息并等待匹配mid的响应

        Args:
            mid: 消息ID
            msg: 消息内容
            timeout: 超时秒数

        Returns:
            响应消息字典
        """
        if not self._ws or self._ws.closed:
            raise Exception("WebSocket未连接")

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[mid] = future

        try:
            await self._ws.send_json(msg)
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise Exception(f"请求超时: {msg.get('lwp', 'unknown')}")
        finally:
            self._pending.pop(mid, None)

    async def _reconnect_with_new_token(self, seen_generation: int) -> bool:
        """Token/连接失效时：标记 Token 缓存过期 → 断开 → 用新 Token 重新连接并注册

        Token 只在建连的 /reg 头里使用一次，因此换 Token 必须重建连接才生效。
        `_mark_cached_token_expired` 会把 xy_token_cache 的到期时间置为过去，
        使 `_get_im_token` 缓存未命中、必然重新调 API 取一个全新 Token。

        Args:
            seen_generation: 调用方发起请求时记录的连接代次，用于并发去重
        Returns:
            是否已具备可用连接（已由其它请求完成重连时也返回 True）
        """
        async with self._reconnect_lock:
            # 已有其它并发请求完成重连：直接复用新连接，不重复断连
            if self._conn_generation != seen_generation:
                logger.info(f"【{self.account_id}】IM 连接已被其它请求重建，直接复用")
                return self.is_connected

            logger.warning(
                f"【{self.account_id}】IM 请求被拒(code=400)，判定 Token/连接失效，"
                f"标记 Token 缓存过期并重连"
            )
            try:
                await self._mark_cached_token_expired()
            except Exception as e:
                logger.warning(f"【{self.account_id}】标记 Token 缓存过期失败（继续重连）: {e}")

            self.token = ""
            await self.disconnect()
            ok = await self.connect()
            if ok:
                self._conn_generation += 1
                logger.info(f"【{self.account_id}】IM 已用新 Token 重连成功")
            else:
                logger.error(f"【{self.account_id}】IM 重连失败，请稍后在界面重新连接该账号")
            return ok

    async def _send_and_wait_with_retry(
        self,
        build_msg,
        *,
        timeout: float = REQUEST_TIMEOUT,
        retry_after_reconnect: bool = True,
    ) -> dict:
        """发送 LWP 请求；遇到 code=400（Token/连接失效）时刷新 Token 重连

        除自身收到 code=400 外，还处理「并发请求已把连接重连」的情况：本次请求可能
        被那次 disconnect() 以「连接已断开」中断（非 ImRequestRejected），此时按同样的
        连接失效语义处理，避免把一次自愈重连暴露成对用户的报错。

        Args:
            build_msg: 无参回调，返回 (mid, msg)。重试时会重新调用以生成新的 mid
            timeout: 单次请求等待响应的超时秒数
            retry_after_reconnect: 重连成功后是否自动重试。
                幂等查询（会话列表/聊天记录）传 True；
                发送/撤回等非幂等操作传 False，只重连不重发，避免重复发送
        Returns:
            响应消息字典
        Raises:
            ImRequestRejected: 非 400 拒绝、重连失败、或不允许自动重试时抛出
            Exception: 与连接失效无关的错误（超时等）原样抛出
        """
        seen_generation = self._conn_generation
        mid, msg = build_msg()
        try:
            return await self._send_and_wait(mid, msg, timeout=timeout)
        except Exception as e:
            is_token_400 = (
                isinstance(e, ImRequestRejected) and e.code in TOKEN_INVALID_LWP_CODES
            )
            # 本次请求期间代次已变 → 有并发请求完成了重连，当前失败极可能是被那次断连中断
            concurrent_reconnected = self._conn_generation != seen_generation
            if not is_token_400 and not concurrent_reconnected:
                raise
            # is_token_400 → 由本请求触发重连；concurrent_reconnected → _reconnect 内部发现
            # 代次已变会直接复用新连接、不再重复断连
            if not await self._reconnect_with_new_token(seen_generation):
                raise
            if not retry_after_reconnect:
                code = e.code if isinstance(e, ImRequestRejected) else None
                raise ImRequestRejected(
                    f"连接已失效，已自动重连（原因: {e}），请重新操作一次", code
                ) from e
            logger.info(f"【{self.account_id}】重连完成，重试 {msg.get('lwp', 'unknown')}")
            mid, msg = build_msg()
            return await self._send_and_wait(mid, msg, timeout=timeout)

    async def _recv_loop(self):
        """后台消息接收循环"""
        try:
            async for ws_msg in self._ws:
                if ws_msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(ws_msg.data)
                elif ws_msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    logger.warning(
                        f"【{self.account_id}】WebSocket连接异常关闭"
                    )
                    self._connected = False
                    break
            else:
                # async for 正常结束（服务端优雅关闭/网络中断，迭代器自然终止，
                # 不产生 CLOSED/ERROR 帧）时同步连接状态，避免标志位卡在 True
                if self._connected:
                    logger.warning(f"【{self.account_id}】WebSocket连接已关闭")
                    self._connected = False
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"【{self.account_id}】消息接收异常: {e}")
            self._connected = False

    def add_push_callback(self, callback):
        """注册推送消息回调（用于向前端转发实时消息）

        Args:
            callback: 异步回调函数，接收解析后的推送消息 dict
        """
        if callback not in self._push_callbacks:
            self._push_callbacks.append(callback)

    def remove_push_callback(self, callback):
        """注销推送消息回调"""
        if callback in self._push_callbacks:
            self._push_callbacks.remove(callback)

    async def _handle_message(self, data: str):
        """处理收到的WebSocket消息"""
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            return

        # 发送ACK
        headers = message.get("headers", {})
        mid = headers.get("mid", generate_mid())
        ack = {
            "code": 200,
            "headers": {
                "mid": mid,
                "sid": headers.get("sid", ""),
            },
        }
        # 复制需要回传的header字段
        for key in ("app-key", "ua", "dt"):
            if key in headers:
                ack["headers"][key] = headers[key]

        try:
            await self._send_raw(ack)
        except Exception:
            pass

        # 匹配等待中的请求
        # 注意：IM数据响应通常没有code字段，匹配到mid就直接resolve
        if mid in self._pending:
            future = self._pending[mid]
            if not future.done():
                code = message.get("code", 200)
                body = message.get("body", {})
                # 记录错误响应的完整内容
                if isinstance(body, dict) and "reason" in body:
                    logger.warning(
                        f"【{self.account_id}】IM请求响应含错误, "
                        f"code={code}, body={json.dumps(body, ensure_ascii=False)[:300]}"
                    )
                if code == 200 or "body" in message:
                    future.set_result(message)
                else:
                    future.set_exception(
                        ImRequestRejected(
                            f"请求失败: code={code}, "
                            f"msg={json.dumps(message, ensure_ascii=False)[:200]}",
                            code,
                        )
                    )
            return

        # 非请求响应 —— 服务器主动推送的消息，解密并记录日志
        await self._handle_push_message(message)

    async def _handle_push_message(self, message: dict):
        """
        处理服务器主动推送的消息

        参照自动回复 message_handler.py 的解密和解析逻辑：
        1. 检查是否为 syncPushPackage（同步推送包）
        2. 解密每条消息（base64 -> JSON 或 decrypt）
        3. 解析聊天消息内容并打印完整日志
        4. 触发已注册的回调，将解析后的消息推送给前端
        """
        try:
            body = message.get("body", {})
            sync_pkg = body.get("syncPushPackage") if isinstance(body, dict) else None
            if not sync_pkg:
                return
            data_list = sync_pkg.get("data", [])
            if not data_list:
                return

            # 延迟初始化解析器
            if not hasattr(self, "_push_parser"):
                self._push_parser = PushMessageParser(self.account_id, self.myid)

            for sync_data in data_list:
                if not isinstance(sync_data, dict) or "data" not in sync_data:
                    continue
                decrypted = self._push_parser.decrypt_push_data(sync_data["data"])
                if decrypted is None:
                    continue
                parsed = self._push_parser.parse(decrypted)
                if parsed is None:
                    continue
                for cb in self._push_callbacks:
                    try:
                        await cb(parsed)
                    except Exception as cb_e:
                        logger.warning(f"【{self.account_id}】推送回调异常: {cb_e}")
        except Exception as e:
            logger.warning(f"【{self.account_id}】处理推送消息异常: {e}")

    async def _heartbeat_loop(self):
        """心跳保活循环"""
        try:
            while self._connected:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if not self._connected or not self._ws or self._ws.closed:
                    break
                try:
                    heartbeat = {
                        "lwp": "/!",
                        "headers": {"mid": generate_mid()},
                    }
                    await self._send_raw(heartbeat)
                except Exception as e:
                    logger.warning(
                        f"【{self.account_id}】心跳发送失败: {e}"
                    )
                    break
        except asyncio.CancelledError:
            pass
