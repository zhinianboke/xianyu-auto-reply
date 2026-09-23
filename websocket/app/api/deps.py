"""
WebSocket 服务 API 依赖。

功能：
1. 统一保护 WebSocket 服务的内部 HTTP API。
2. 使用独立的服务间令牌，避免把用户 JWT 暴露给内部服务调用。
"""
from __future__ import annotations

from fastapi import Request

from app.core.config import get_settings
from common.utils.internal_auth import INTERNAL_AUTH_HEADER, require_valid_internal_token


async def require_internal_auth(request: Request) -> None:
    """校验 /internal 请求的服务间令牌。"""
    settings = get_settings()
    provided = request.headers.get(INTERNAL_AUTH_HEADER)
    require_valid_internal_token(provided, settings.internal_api_token)
