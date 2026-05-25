"""
推广返佣系统 - 认证服务

功能：
1. 用户名密码认证
2. 登录失败次数限制（最大3次，锁定2小时）
3. 登录时间记录
4. 访问令牌/刷新令牌生成
"""
from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from typing import Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from common.models.user import User
from common.utils.time_utils import BEIJING_TZ, get_beijing_now

# 登录失败限制配置
MAX_LOGIN_FAIL_COUNT = 3
LOGIN_LOCK_HOURS = 2


class AuthService:
    """推广返佣系统认证服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    def _check_login_locked(self, user: User) -> Tuple[bool, Optional[str]]:
        """
        检查用户是否被锁定
        返回: (是否锁定, 锁定提示信息)
        """
        if user.login_locked_until:
            now = get_beijing_now()
            locked_until = user.login_locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=BEIJING_TZ)

            if locked_until > now:
                remaining = locked_until - now
                remaining_minutes = int(remaining.total_seconds() / 60)
                if remaining_minutes > 60:
                    remaining_str = f"{remaining_minutes // 60}小时{remaining_minutes % 60}分钟"
                else:
                    remaining_str = f"{remaining_minutes}分钟"
                return True, f"账号已被锁定，请{remaining_str}后再试"
        return False, None

    async def _handle_login_fail(self, user: User) -> str:
        """处理登录失败，增加失败次数"""
        user.login_fail_count = (user.login_fail_count or 0) + 1
        remaining_attempts = MAX_LOGIN_FAIL_COUNT - user.login_fail_count

        if user.login_fail_count >= MAX_LOGIN_FAIL_COUNT:
            user.login_locked_until = get_beijing_now() + timedelta(hours=LOGIN_LOCK_HOURS)
            await self.session.flush()
            await self.session.commit()
            return f"密码错误次数过多，账号已被锁定{LOGIN_LOCK_HOURS}小时"

        await self.session.flush()
        await self.session.commit()
        return f"用户名或密码错误，还剩{remaining_attempts}次尝试机会"

    async def _reset_login_fail(self, user: User) -> None:
        """登录成功后重置失败次数"""
        if user.login_fail_count > 0 or user.login_locked_until:
            user.login_fail_count = 0
            user.login_locked_until = None
            await self.session.flush()

    async def authenticate_by_username(self, username: str, password: str) -> Tuple[Optional[User], Optional[str]]:
        """
        通过用户名认证
        返回: (用户对象, 错误信息)
        """
        if not username:
            return None, "请输入用户名"
        stmt = select(User).where(func.lower(User.username) == username.lower())
        user = (await self.session.execute(stmt)).scalar_one_or_none()

        if not user:
            return None, "用户名或密码错误"

        # 检查是否被锁定
        is_locked, lock_msg = self._check_login_locked(user)
        if is_locked:
            return None, lock_msg

        # 验证密码
        if not self._verify_user_password(user, password):
            error_msg = await self._handle_login_fail(user)
            return None, error_msg

        # 登录成功，重置失败次数
        await self._reset_login_fail(user)
        return user, None

    def _verify_user_password(self, user: User, password: Optional[str]) -> bool:
        """验证用户密码"""
        if not password:
            return False
        stored_hash = (user.password_hash or "").strip()
        if len(stored_hash) == 64 and all(c in "0123456789abcdefABCDEF" for c in stored_hash):
            return sha256(password.encode("utf-8")).hexdigest() == stored_hash.lower()
        return security.verify_password(password, stored_hash)

    async def mark_login(self, user: User) -> None:
        """记录登录时间"""
        user.last_login_at = get_beijing_now()
        await self.session.flush()
        await self.session.commit()

    def create_access_token(self, user: User) -> str:
        """创建访问令牌"""
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
        """创建刷新令牌"""
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role.value,
        }
        return security.create_refresh_token(
            payload,
            expires_delta=timedelta(minutes=self.settings.refresh_token_expire_minutes),
        )
