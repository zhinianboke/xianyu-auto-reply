"""
Scheduler API 依赖

功能：
1. 校验服务间 /internal API 共享令牌
2. 阻止未认证请求访问任务控制接口
"""
from __future__ import annotations

from fastapi import Request

from app.core.config import get_settings
from common.utils.internal_auth import INTERNAL_AUTH_HEADER, require_valid_internal_token


async def require_internal_auth(request: Request) -> None:
    """校验 /internal 请求携带的服务间令牌。"""
    settings = get_settings()
    provided = request.headers.get(INTERNAL_AUTH_HEADER)
    require_valid_internal_token(provided, settings.internal_api_token)
