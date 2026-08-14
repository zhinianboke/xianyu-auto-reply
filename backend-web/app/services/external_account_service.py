"""
公开账号访问服务。

功能：
1. 根据个人设置中的分销秘钥定位所属用户。
2. 返回该用户账号管理中所有已启用账号的账号 ID 和备注。
3. 校验公开接口指定的账号是否属于该用户且处于启用状态。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.user import User
from common.models.xy_account import XYAccount


class ExternalAccountAccessError(RuntimeError):
    """公开接口访问账号失败时抛出的业务异常。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ExternalAccountService:
    """使用分销秘钥查询用户已启用的闲鱼账号。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _is_account_enabled(account: XYAccount) -> bool:
        """
        判断账号是否符合账号管理中的启用口径。

        Args:
            account: 闲鱼账号记录。
        Returns:
        账号发布链路实际可用时返回 True。
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
        return (
            await self.session.execute(
                select(User.id).where(User.secret_key == secret_key.strip()).limit(1)
            )
        ).scalar_one_or_none()

    async def list_enabled_accounts_by_secret(self, secret_key: str) -> list[dict[str, str]] | None:
        """
        根据分销秘钥查询所属用户的已启用账号。

        Args:
            secret_key: 个人设置-分销管理中的分销秘钥。
        Returns:
            秘钥不存在时返回 None；匹配时返回账号 ID 和备注列表。
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
            }
            for account in accounts
            if self._is_account_enabled(account)
        ]

    async def get_enabled_account_by_secret(
        self,
        secret_key: str,
        account_id: str,
    ) -> XYAccount:
        """
        获取分销秘钥所属用户的指定启用账号。

        Args:
            secret_key: 个人设置-分销管理中的分销秘钥。
            account_id: 上一个公开账号列表接口返回的闲鱼账号 ID。
        Returns:
            已确认归属且处于启用状态的账号记录。
        Raises:
            ExternalAccountAccessError: 秘钥、账号归属或启用状态校验失败。
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
        if not self._is_account_enabled(account):
            raise ExternalAccountAccessError(40003, "闲鱼账号未启用")
        return account


__all__ = ["ExternalAccountAccessError", "ExternalAccountService"]
