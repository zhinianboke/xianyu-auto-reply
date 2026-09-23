"""
公开账号访问服务。

功能：
1. 根据个人设置中的分销秘钥定位所属用户。
2. 返回该用户账号管理中全部账号的账号 ID、备注和启用状态（含禁用账号）。
3. 校验公开接口指定的账号是否属于该秘钥用户，不限制账号启用状态。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.user import User, UserStatus
from common.models.xy_account import XYAccount


class ExternalAccountAccessError(RuntimeError):
    """公开接口访问账号失败时抛出的业务异常。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ExternalAccountService:
    """使用分销秘钥查询用户名下的闲鱼账号。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _is_account_enabled(account: XYAccount) -> bool:
        """
        判断账号是否处于启用状态，仅用于账号列表的状态标识。

        公开接口不用该结果拦截调用，禁用账号同样允许调用分类和发布接口。

        Args:
            account: 闲鱼账号记录。
        Returns:
            状态为 active 时返回 True，其余状态一律视为禁用。
        """
        return (account.status or "").strip().lower() == "active"

    async def _get_owner_id_by_secret(self, secret_key: str) -> int | None:
        """
        根据分销秘钥查询所属用户 ID。

        Args:
            secret_key: 个人设置-分销管理中的分销秘钥。
        Returns:
            秘钥不存在时返回 None，否则返回用户 ID。
        """
        user = (
            await self.session.execute(
                select(User).where(User.secret_key == secret_key.strip()).limit(1)
            )
        ).scalar_one_or_none()
        if user is None or user.status == UserStatus.DELETED:
            return None
        return user.id

    async def get_user_by_secret(self, secret_key: str) -> User | None:
        """根据分销秘钥获取用户对象，未找到时返回 ``None``。"""
        return (
            await self.session.execute(
                select(User).where(User.secret_key == secret_key.strip()).limit(1)
            )
        ).scalar_one_or_none()

    async def list_accounts_by_secret(self, secret_key: str) -> list[dict[str, Any]] | None:
        """
        根据分销秘钥查询所属用户的全部账号（含禁用账号）。

        Args:
            secret_key: 个人设置-分销管理中的分销秘钥。
        Returns:
            秘钥不存在时返回 None；匹配时返回账号列表，每项含账号 ID、备注、
            enabled 启用标识、status 原始状态和 disable_reason 禁用原因。
            enabled 仅作状态展示，禁用账号同样可以调用公开分类和发布接口。
        """
        owner_id = await self._get_owner_id_by_secret(secret_key)
        if owner_id is None:
            return None

        accounts = (
            await self.session.execute(
                select(XYAccount)
                .where(XYAccount.owner_id == owner_id)
                .order_by(XYAccount.account_id)
            )
        ).scalars().all()
        return [
            {
                "account_id": str(account.account_id),
                "remark": (account.remark or "").strip(),
                # 仅供调用方展示账号状态，不影响公开分类和发布接口的放行
                "enabled": self._is_account_enabled(account),
                "status": (account.status or "").strip(),
                "status_name": "启用" if self._is_account_enabled(account) else "禁用",
                "disable_reason": (account.disable_reason or "").strip(),
            }
            for account in accounts
        ]

    async def get_account_by_secret(
        self,
        secret_key: str,
        account_id: str,
    ) -> XYAccount:
        """
        获取分销秘钥所属用户的指定账号，不校验启用状态。

        公开接口只做归属校验：禁用账号也允许调用分类和发布接口，
        Cookie 失效等问题由平台调用结果如实返回给调用方。

        Args:
            secret_key: 个人设置-分销管理中的分销秘钥。
            account_id: 上一个公开账号列表接口返回的闲鱼账号 ID。
        Returns:
            已确认归属该秘钥用户的账号记录。
        Raises:
            ExternalAccountAccessError: 秘钥不存在或账号不属于该用户。
        """
        owner_id = await self._get_owner_id_by_secret(secret_key)
        if owner_id is None:
            raise ExternalAccountAccessError(40001, "秘钥不存在")

        account = (
            await self.session.execute(
                select(XYAccount)
                .where(
                    XYAccount.owner_id == owner_id,
                    XYAccount.account_id == account_id.strip(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if account is None:
            raise ExternalAccountAccessError(40002, "闲鱼账号不存在或不属于该秘钥用户")
        return account


__all__ = ["ExternalAccountAccessError", "ExternalAccountService"]
