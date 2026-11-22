"""
HTTP 请求工具

功能：
1. get_client_ip：兼容旧调用点，统一委托公共可信代理客户端 IP 校验。
"""
from __future__ import annotations

from starlette.requests import HTTPConnection

from common.core.request_meta import client_ip


def get_client_ip(request: HTTPConnection) -> str | None:
    """获取可信客户端 IP；参数为 HTTP/WebSocket 连接，无法识别时返回 None。"""
    return client_ip(request)
