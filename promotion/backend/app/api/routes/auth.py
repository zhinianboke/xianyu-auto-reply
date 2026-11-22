"""
推广返佣系统 - 认证API路由

功能：
1. 用户登录（用户名密码，与主系统共用限流和账号锁）
2. 令牌验证
3. 令牌刷新
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.routes.geetest import check_geetest_verified
from app.core.security import decode_token
from app.services.auth_service import AuthService
from common.models.user import User, UserRole, UserStatus
from common.schemas.auth import LoginRequest, LoginResponse, TokenPayload
from common.services.auth_request_validation import AuthenticationAPIRoute
from common.services.login_flow_service import perform_login
from common.services.login_settings_service import load_login_settings
from common.services.user_login_log_service import (
    LOGIN_METHOD_USERNAME_PASSWORD,
    UserLoginLogService,
)
from common.utils.http_utils import get_client_ip

router = APIRouter(tags=["认证"], route_class=AuthenticationAPIRoute)


@router.post("/login", response_model=LoginResponse)
async def login_user(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(deps.get_db_session),
) -> LoginResponse:
    """执行用户名密码登录；计数、锁定、后缀和审计与主系统共享。"""
    auth_service = AuthService(session)
    return await perform_login(
        payload, get_client_ip(request), auth_service, session, UserLoginLogService(session),
        captcha_check=check_geetest_verified, settings_loader=load_login_settings,
        supported_login_methods=frozenset({LOGIN_METHOD_USERNAME_PASSWORD}),
    )


@router.get("/verify")
async def verify_token(
    current_user: User = Depends(deps.get_current_active_user),
):
    """验证令牌有效性"""
    return {
        "authenticated": True,
        "user_id": current_user.id,
        "username": current_user.username,
        "is_admin": current_user.role == UserRole.ADMIN,
        "account_limit": current_user.account_limit,
    }


@router.post("/refresh")
async def refresh_token(
    token: str = Depends(deps.oauth2_scheme),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """刷新令牌"""
    try:
        payload = TokenPayload(**decode_token(token))
    except (Exception, ValueError):
        return {"success": False, "message": "令牌无效"}

    if payload.sub is None:
        return {"success": False, "message": "令牌无效"}

    result = await session.execute(select(User).where(User.id == int(payload.sub)))
    user = result.scalar_one_or_none()

    if not user or user.status != UserStatus.ACTIVE:
        return {"success": False, "message": "用户不存在或已禁用"}

    auth_service = AuthService(session)

    return {
        "success": True,
        "token": auth_service.create_access_token(user),
        "refresh_token": auth_service.create_refresh_token(user),
        "user_id": user.id,
        "username": user.username,
        "is_admin": user.role == UserRole.ADMIN,
        "account_limit": user.account_limit,
    }
