"""系统用户认证公共基类：统一密码校验、连续失败锁定和成功事务内清零。

主系统与推广系统共用用户表和此实现；只锁定、刷新，不独立提交业务事务。
"""
from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from math import ceil

from loguru import logger
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.user import User, UserStatus
from common.services.auth_rate_limit_service import (
    LOGIN_CONSECUTIVE_MAX_FAILURES,
    LOGIN_LOCK_HOURS,
)
from common.utils.security import verify_password
from common.utils.time_utils import BEIJING_TZ, get_beijing_now_naive


class UserAuthenticationRejected(ValueError):
    """账号不存在、被禁用或被锁定；由登录入口返回中文业务错误并提交审计。"""

    code = 40001


class UserAuthService:
    """使用调用方会话认证系统用户；各系统派生类仅保留配置和令牌签发。"""

    def __init__(self, session: AsyncSession):
        """保存当前请求会话，不创建引擎、连接池或跨请求会话。"""
        self.session = session

    async def find_login_user(self, account: str, *, by_email: bool = False) -> User | None:
        """按用户名或邮箱不区分大小写查询用户，供限流身份和失败审计使用。

        Args:
            account: 请求中的用户名或邮箱。
            by_email: 为真时按邮箱查询，否则按用户名查询。
        Returns:
            已存在的用户或None；不校验密码、不修改失败计数。
        """
        if not account:
            return None
        column = User.email if by_email else User.username
        result = await self.session.execute(select(User).where(func.lower(column) == account.lower()))
        return result.scalar_one_or_none()

    async def _load_user_for_update(self, user: User) -> User:
        """按已识别用户编号当前锁读并刷新缓存，返回存在的用户或抛出业务拒绝。"""
        # 请求异常后rollback会过期ORM字段，使用identity避免访问user.id触发隐式异步IO。
        identity = inspect(user).identity
        user_id = identity[0] if identity else user.id
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        current = result.scalar_one_or_none()
        if current is None:
            raise UserAuthenticationRejected("账号不存在，请重新登录")
        return current

    @staticmethod
    def _locked_until(user: User):
        """将历史锁定时间统一为北京时间无时区值；空值返回None，不修改历史数据。"""
        value = user.login_locked_until
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(BEIJING_TZ).replace(tzinfo=None)
        return value

    def _lock_message(self, user: User, now) -> str | None:
        """返回当前有效锁的剩余时间提示；锁已到期或未设置时返回None。"""
        locked_until = self._locked_until(user)
        if locked_until is None or locked_until <= now:
            return None
        minutes = max(1, ceil((locked_until - now).total_seconds() / 60))
        hours, remaining_minutes = divmod(minutes, 60)
        duration = f"{hours}小时" if hours else ""
        if remaining_minutes:
            duration += f"{remaining_minutes}分钟"
        return f"账号已被锁定，请{duration}后再试"

    def _clear_expired_lock(self, user: User, now) -> bool:
        """仅在本次已持锁请求发现锁到期时清除旧计数，返回是否发生惰性解锁。"""
        locked_until = self._locked_until(user)
        if locked_until is None or locked_until > now:
            return False
        user.login_fail_count = 0
        user.login_locked_until = None
        user.updated_at = now
        logger.info("登录锁定到期，当前请求惰性解锁: user_id={}", user.id)
        return True

    def _require_login_allowed(self, user: User, now) -> None:
        """校验已锁读账号的状态和有效锁，仅抛业务拒绝，不修改账号字段。"""
        if user.status != UserStatus.ACTIVE:
            raise UserAuthenticationRejected("账号已禁用，请联系管理员")
        message = self._lock_message(user, now)
        if message:
            raise UserAuthenticationRejected(message)

    async def lock_login_user(self, user: User) -> User:
        """当前锁读并校验账号状态和锁；有效锁绝不能被旧认证结果绕过。

        Args:
            user: 已根据请求身份查到的用户对象。
        Returns:
            刷新后的可登录用户；拒绝时抛UserAuthenticationRejected，不提交事务。
        """
        current = await self._load_user_for_update(user)
        now = get_beijing_now_naive()
        self._require_login_allowed(current, now)
        if self._clear_expired_lock(current, now):
            await self.session.flush()
        return current

    def _verify_user_password(self, user: User, password: str | None) -> bool:
        """验证既有SHA256、bcrypt或passlib密码，不修改用户、不记录原始密码。"""
        if not password:
            return False
        stored_hash = (user.password_hash or "").strip()
        if len(stored_hash) == 64 and all(c in "0123456789abcdefABCDEF" for c in stored_hash):
            return sha256(password.encode("utf-8", errors="surrogatepass")).hexdigest() == stored_hash.lower()
        try:
            return verify_password(password, stored_hash)
        except UnicodeError:
            # JSON可携带孤立Unicode代理字符，非法密码仍属于认证失败，不能绕过计数。
            return False

    async def _authenticate(self, account: str, password: str, *, by_email: bool):
        """共用两种密码认证，仅校验当前账号和密码；失败计数由统一登录收尾执行。"""
        if not account:
            return None, "请输入邮箱" if by_email else "请输入用户名"
        user = await self.find_login_user(account, by_email=by_email)
        invalid_message = "邮箱或密码错误" if by_email else "用户名或密码错误"
        if user is None:
            return None, invalid_message
        try:
            current = await self._load_user_for_update(user)
            # 密码认证只读取当前状态；到期计数由入口锁检查或最终收尾惰性清除。
            self._require_login_allowed(current, get_beijing_now_naive())
        except UserAuthenticationRejected as exc:
            return None, str(exc)
        if not self._verify_user_password(current, password):
            return None, invalid_message
        return current, None

    async def authenticate_by_username(self, username: str, password: str) -> tuple[User | None, str | None]:
        """校验用户名密码；返回用户与错误提示，不计失败、不清零、不提交事务。"""
        return await self._authenticate(username, password, by_email=False)

    async def authenticate_by_email(self, email: str, password: str) -> tuple[User | None, str | None]:
        """校验邮箱密码；返回用户与错误提示，与用户名认证使用同一账号锁。"""
        return await self._authenticate(email, password, by_email=True)

    async def record_login_failure(self, user: User) -> str:
        """当前锁读原子累加一次连续失败；第五次锁三小时，已锁请求不延长锁。

        Args:
            user: 本次失败对应的已识别用户，三种登录方式必须共用此方法。
        Returns:
            剩余机会或锁定提示；仅刷新，调用方与登录日志一起提交或回滚。
        """
        current = await self._load_user_for_update(user)
        now = get_beijing_now_naive()
        message = self._lock_message(current, now)
        if message:
            logger.info("已锁定账号拒绝登录，保留原锁期限: user_id={}", current.id)
            return message
        self._clear_expired_lock(current, now)
        current.login_fail_count = (current.login_fail_count or 0) + 1
        current.updated_at = now
        remaining = LOGIN_CONSECUTIVE_MAX_FAILURES - current.login_fail_count
        if remaining <= 0:
            current.login_locked_until = now + timedelta(hours=LOGIN_LOCK_HOURS)
            message = f"登录失败次数过多，账号已被锁定{LOGIN_LOCK_HOURS}小时"
        else:
            message = f"登录失败，还剩{remaining}次尝试机会"
        await self.session.flush()
        logger.info("记录账号连续登录失败: user_id={}, failure_count={}, locked_until={}",
                    current.id, current.login_fail_count, current.login_locked_until)
        return message

    async def reset_login_failure(self, user: User) -> User:
        """成功最终事务内重查锁、清零失败计数并更新时间，禁止用旧成功解锁有效锁。

        Args:
            user: 已认证的用户；提交前仍需验证当前状态和账号锁。
        Returns:
            刷新并清零后的用户；仅刷新，事务由成功审计流程负责。
        """
        current = await self.lock_login_user(user)
        now = get_beijing_now_naive()
        current.login_fail_count = 0
        current.login_locked_until = None
        current.last_login_at = now
        current.updated_at = now
        await self.session.flush()
        logger.info("登录成功事务清零连续失败计数: user_id={}", current.id)
        return current
