"""
HTTP 请求工具

功能：
1. get_client_ip：从请求中提取客户端真实 IP（优先 X-Forwarded-For，其次 X-Real-IP，最后回落到直连地址）
"""
from __future__ import annotations

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """获取客户端真实 IP 地址。

    兼容 Nginx 等反向代理场景，优先级：
    1. X-Forwarded-For（取最左侧首个地址）
    2. X-Real-IP
    3. 直连 socket 地址

    Args:
        request: FastAPI 请求对象
    Returns:
        客户端 IP 字符串；无法获取时返回 "-"
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "-"