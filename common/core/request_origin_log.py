"""请求来源访问日志：纯 ASGI 透传 HTTP/WebSocket，保留可信客户端与实际连接对端。"""
# Ruff按标准logging检查bind返回值；这里明确使用Loguru的花括号参数格式。
# ruff: noqa: PLE1205
from __future__ import annotations

import asyncio
from uuid import uuid4

from loguru import logger
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from common.core.request_meta import format_request_origin


class RequestOriginLoggingMiddleware:
    """记录所有 HTTP/WebSocket 访问来源；不读取请求体、不缓存响应流、不处理生命周期。"""

    def __init__(self, app: ASGIApp) -> None:
        """参数为下游 ASGI 应用；保存原应用，后续仅包装消息收发以记录来源。"""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """参数为 ASGI 连接和收发函数；原样透传消息，记录开始、结果、关闭及异常堆栈。"""
        connection_type = scope["type"]
        if connection_type not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        request_id = state.setdefault("request_id", uuid4().hex)
        origin = format_request_origin(scope)
        metadata = "method={!r} path={!r} query={!r}".format(
            scope.get("method", "WEBSOCKET"),
            scope.get("path", ""),
            scope.get("query_string", b"").decode("latin-1"),
        )
        log = logger.bind(request_id=request_id, operation="request_origin")
        status: int | None = None
        accepted = False
        closed = False
        response_complete = False
        log.info("[来源访问] 开始 type={} request_id={} {} origin={}", connection_type, request_id, metadata, origin)

        async def send_with_log(message: Message) -> None:
            """接收下游消息并原样发送；仅观察状态和关闭事件，不访问或改写通信载荷。"""
            nonlocal status, accepted, closed, response_complete
            await send(message)
            message_type = message["type"]
            if message_type == "http.response.start":
                status = message["status"]
            elif message_type == "http.response.body" and not message.get("more_body", False):
                response_complete = True
            elif message_type == "websocket.accept":
                accepted = True
                log.info("[WebSocket来源] 握手接受 request_id={} {} origin={}", request_id, metadata, origin)
            elif message_type == "websocket.http.response.start":
                status = message["status"]
                log.info("[WebSocket来源] 握手拒绝 request_id={} {} status={} origin={}", request_id, metadata, status, origin)
            elif message_type == "websocket.close":
                closed = True
                event = "关闭" if accepted else "握手拒绝"
                log.info(
                    "[WebSocket来源] {} request_id={} {} code={} reason={!r} origin={}",
                    event, request_id, metadata, message.get("code"), message.get("reason", ""), origin,
                )

        async def receive_with_log() -> Message:
            """接收并原样返回上游消息；只记录 WebSocket 客户端断连，不读取业务消息载荷。"""
            nonlocal closed
            message = await receive()
            if message["type"] == "websocket.disconnect" and not closed:
                closed = True
                log.info(
                    "[WebSocket来源] 客户端关闭 request_id={} {} code={} reason={!r} origin={}",
                    request_id, metadata, message.get("code"), message.get("reason", ""), origin,
                )
            return message

        with logger.contextualize(request_id=request_id):
            try:
                await self.app(scope, receive_with_log, send_with_log)
            except asyncio.CancelledError:
                log.warning("[来源访问] 请求取消 type={} request_id={} {} status={} origin={}", connection_type, request_id, metadata, status, origin)
                raise
            except Exception:
                # 外层 ServerErrorMiddleware 可能尚未生成错误响应；未知状态保留 None，不猜测状态码。
                log.exception("[来源访问] 未处理异常 type={} request_id={} {} status={} origin={}", connection_type, request_id, metadata, status, origin)
                raise
            else:
                if connection_type == "http":
                    log.info(
                        "[HTTP来源] 返回 request_id={} {} status={} complete={} origin={}",
                        request_id, metadata, status, response_complete, origin,
                    )
                elif not closed:
                    log.info("[WebSocket来源] 应用返回 request_id={} {} accepted={} status={} origin={}", request_id, metadata, accepted, status, origin)
