"""
推广返佣系统 - FastAPI依赖注入模块

功能：
1. 提供数据库会话依赖
2. 提供用户认证依赖（当前用户、活跃用户、管理员用户）
3. 提供服务类依赖注入
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_token
from common.db.session import async_session_maker
from common.models import User, UserRole, UserStatus
from common.schemas.auth import TokenPayload

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话"""
    async with async_session_maker() as session:
        yield session


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = TokenPayload(**decode_token(token))
    except (JWTError, ValueError):
        raise credentials_exception
    if payload.sub is None:
        raise credentials_exception

    from sqlalchemy import select
    result = await session.execute(select(User).where(User.id == int(payload.sub)))
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """获取当前活跃用户"""
    if current_user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return current_user


async def get_current_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """获取当前管理员用户"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user


def get_auth_service(session: AsyncSession = Depends(get_db_session)):
    """获取认证服务"""
    from app.services.auth_service import AuthService
    return AuthService(session)
