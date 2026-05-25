"""
推广返佣系统 - 认证API路由

功能：
1. 用户登录（用户名+密码）
2. 令牌验证
3. 令牌刷新
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import decode_token
from common.models.user import User, UserRole, UserStatus
from common.schemas.auth import TokenPayload

router = APIRouter(tags=["认证"])


@router.post("/login")
async def login_user(
    payload: dict,
    session: AsyncSession = Depends(deps.get_db_session),
):
    """
    用户登录

    支持用户名+密码登录，集成极验滑动验证码校验
    """
    from app.services.auth_service import AuthService
    auth_service = AuthService(session)

    username = payload.get("username")
    password = payload.get("password")

    if not username or not password:
        return {"success": False, "message": "请输入用户名和密码"}

    # 检查是否启用了登录滑动验证码
    from sqlalchemy import select as sa_select
    from common.models.system_setting import SystemSetting
    try:
        captcha_result = await session.execute(
            sa_select(SystemSetting.value).where(SystemSetting.key == "login_captcha_enabled")
        )
        captcha_enabled_str = captcha_result.scalar_one_or_none()
        # 默认开启
        captcha_enabled = captcha_enabled_str in (None, "true", "1")
    except Exception:
        captcha_enabled = True

    # 如果启用了验证码，校验极验滑动验证
    if captcha_enabled:
        from app.api.routes.geetest import check_geetest_verified

        geetest_challenge = payload.get("geetest_challenge")
        if not geetest_challenge:
            return {"success": False, "message": "请完成滑动验证"}

        geetest_ok, geetest_msg = check_geetest_verified(geetest_challenge)
        if not geetest_ok:
            return {"success": False, "message": geetest_msg}

    user, error_message = await auth_service.authenticate_by_username(username, password)

    if not user:
        return {"success": False, "message": error_message or "登录失败"}

    if user.status != UserStatus.ACTIVE:
        return {"success": False, "message": "账号已禁用，请联系管理员"}

    await auth_service.mark_login(user)
    return {
        "success": True,
        "message": "登录成功",
        "token": auth_service.create_access_token(user),
        "refresh_token": auth_service.create_refresh_token(user),
        "user_id": user.id,
        "username": user.username,
        "is_admin": user.role == UserRole.ADMIN,
        "account_limit": user.account_limit,
    }


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

    from sqlalchemy import select
    result = await session.execute(select(User).where(User.id == int(payload.sub)))
    user = result.scalar_one_or_none()

    if not user or user.status != UserStatus.ACTIVE:
        return {"success": False, "message": "用户不存在或已禁用"}

    from app.services.auth_service import AuthService
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
