"""推广系统认证适配：共用账号认证与锁定逻辑，保留推广系统令牌配置。"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from common.models.user import User
from common.services.user_auth_service import UserAuthService


class AuthService(UserAuthService):
    """复用公共用户认证逻辑，并保留当前服务的令牌签发行为。"""

    def __init__(self, session: AsyncSession):
        """参数为请求会话；初始化公共认证服务和本服务的令牌配置。"""
        super().__init__(session)
        self.settings = get_settings()

    def create_access_token(self, user: User) -> str:
        """根据用户身份签发访问令牌；使用推广系统配置，返回令牌文本。"""
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role.value,
        }
        return security.create_access_token(
            payload,
            expires_delta=timedelta(minutes=self.settings.access_token_expire_minutes),
        )

    def create_refresh_token(self, user: User) -> str:
        """根据用户身份签发刷新令牌；使用推广系统配置，返回令牌文本。"""
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role.value,
        }
        return security.create_refresh_token(
            payload,
            expires_delta=timedelta(minutes=self.settings.refresh_token_expire_minutes),
        )
