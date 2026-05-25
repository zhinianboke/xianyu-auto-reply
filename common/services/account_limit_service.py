"""
账号数量限制服务

功能：
1. 统一读取用户可添加账号数量配置
2. 统计用户当前已添加账号数量
3. 在创建新账号前执行额度校验
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.user import User
from common.models.xy_account import XYAccount


class AccountLimitExceededError(ValueError):
    """账号数量超限异常"""

    def __init__(self, account_limit: int, used_count: int):
        self.account_limit = account_limit
        self.used_count = used_count
        super().__init__(
            f"可添加账号数量已达上限，当前已添加 {used_count} 个，最多可添加 {account_limit} 个"
        )


class AccountLimitService:
    """账号数量限制业务服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_status(self, owner_id: int) -> dict[str, int | None]:
        user = await self.session.get(User, owner_id)
        if not user:
            raise ValueError("用户不存在")

        result = await self.session.execute(
            select(func.count()).select_from(XYAccount).where(XYAccount.owner_id == owner_id)
        )
        used_count = result.scalar() or 0
        account_limit = int(user.account_limit) if user.account_limit is not None else None
        return {
            "account_limit": account_limit,
            "used_count": used_count,
            "remaining_count": max(account_limit - used_count, 0) if account_limit is not None else None,
        }

    async def ensure_can_add_account(self, owner_id: int) -> dict[str, int | None]:
        status = await self.get_status(owner_id)
        remaining_count = status["remaining_count"]
        if remaining_count is not None and remaining_count <= 0:
            raise AccountLimitExceededError(int(status["account_limit"] or 0), status["used_count"])
        return status
