"""

用户服务



功能：

1. 用户CRUD操作

2. 用户查询（按ID、用户名）

3. 用户创建（密码哈希）

4. 用户信息更新

"""

from __future__ import annotations



from datetime import datetime, timedelta

from typing import Optional



from sqlalchemy import func, select

from sqlalchemy.ext.asyncio import AsyncSession



from app.core import security

from common.models.system_setting import SystemSetting

from common.models.user import User, UserRole, UserStatus

from common.models.xy_account import XYAccount

from common.schemas.user import AdminUserCreate, AdminUserUpdate, UserCreate, UserUpdate

from common.utils.time_utils import get_beijing_now_naive





class UserService:

    """User management helper."""



    def __init__(self, session: AsyncSession):

        self.session = session



    async def get(self, user_id: int) -> Optional[User]:

        return await self.session.get(User, user_id)



    async def get_by_username(self, username: str) -> Optional[User]:

        stmt = select(User).where(User.username == username)

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()



    async def get_by_email(self, email: str) -> Optional[User]:

        """根据邮箱查询用户"""

        stmt = select(User).where(User.email == email)

        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()



    async def list(self, *, limit: int = 50, offset: int = 0) -> list[User]:

        stmt = select(User).offset(offset).limit(limit).order_by(User.id)

        results = await self.session.execute(stmt)

        return results.scalars().all()



    async def count_accounts(self, user_id: int) -> int:

        stmt = select(func.count()).select_from(XYAccount).where(XYAccount.owner_id == user_id)

        result = await self.session.execute(stmt)

        return result.scalar() or 0



    async def get_account_limit_status(self, user: User) -> tuple[int | None, int, int | None]:

        account_limit = int(user.account_limit) if user.account_limit is not None else None

        used_count = await self.count_accounts(user.id)

        remaining_count = max(account_limit - used_count, 0) if account_limit is not None else None

        return account_limit, used_count, remaining_count



    async def create_admin_user(self, payload: AdminUserCreate) -> User:

        user = User(

            username=payload.username,

            email=payload.email,

            phone=payload.phone,

            password_hash=security.get_password_hash(payload.password),

            role=payload.role,

            status=payload.status,

            account_limit=payload.account_limit,

            expire_at=payload.expire_at,

        )

        self.session.add(user)

        await self.session.flush()

        await self.session.commit()

        await self.session.refresh(user)

        return user



    async def _calc_register_expire_at(self) -> Optional[datetime]:

        """根据系统设置「注册用户默认天数」计算注册用户的到期日。

        读取 xy_system_settings.user.register_default_days：

        - 为空 / 非正整数：返回 None（不设置到期日，永不过期）

        - 正整数 N：返回 当前北京时间 + N 天（精确到秒）

        Returns:

            到期日（naive datetime，北京时间）或 None

        """

        stmt = select(SystemSetting.value).where(

            SystemSetting.key == "user.register_default_days"

        )

        result = await self.session.execute(stmt)

        raw = result.scalar_one_or_none()

        value = str(raw or "").strip()

        if not value.isdigit():

            return None

        days = int(value)

        if days <= 0:

            return None

        return get_beijing_now_naive() + timedelta(days=days)



    async def create(self, payload: UserCreate, *, role: UserRole | None = None) -> User:

        # 注册时按系统设置的默认天数计算到期日（未配置则为 None，表示永不过期）

        expire_at = await self._calc_register_expire_at()

        user = User(

            username=payload.username,

            email=payload.email,

            phone=payload.phone,

            password_hash=security.get_password_hash(payload.password),

            role=role or UserRole.MEMBER,

            status=UserStatus.ACTIVE,

            expire_at=expire_at,

        )

        self.session.add(user)

        await self.session.flush()

        await self.session.commit()

        return user



    async def update(self, user: User, payload: UserUpdate) -> User:

        for field, value in payload.model_dump(exclude_unset=True).items():

            setattr(user, field, value)

        await self.session.flush()

        await self.session.commit()

        return user



    async def update_admin_user(self, user: User, payload: AdminUserUpdate) -> User:

        data = payload.model_dump(exclude_unset=True)

        password = data.pop("password", None)

        for field, value in data.items():

            setattr(user, field, value)

        if password:

            user.password_hash = security.get_password_hash(password)

        await self.session.flush()

        await self.session.commit()

        await self.session.refresh(user)

        return user

