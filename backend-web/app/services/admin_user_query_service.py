"""管理员用户查询服务：统一分页筛选、角色字典、余额查询与用户返回数据。"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.user_role_dictionary import USER_ROLE_DICTIONARY
from common.models.data_dictionary import XYDataDictionary
from common.models.user import User, UserRole
from common.models.user_setting import UserSetting
from common.models.xy_account import XYAccount
from common.services.settlement_service import BALANCE_KEY
from common.utils.time_utils import safe_isoformat


def _format_balance(value: str | None) -> str:
    """保留原有余额展示规则；接收存储值，返回两位小数的余额字符串。"""
    if value is None:
        return "0.00"
    try:
        return f"{Decimal(str(value)):.2f}"
    except (InvalidOperation, ValueError):
        return "0.00"


async def fetch_user_balances(session: AsyncSession, user_ids: list[int]) -> dict[int, str]:
    """通过请求会话批量读取指定用户余额，返回用户ID到余额原始值的映射。"""
    if not user_ids:
        return {}
    stmt = select(UserSetting.user_id, UserSetting.value).where(
        UserSetting.key == BALANCE_KEY,
        UserSetting.user_id.in_(user_ids),
    )
    return {user_id: value for user_id, value in (await session.execute(stmt)).all()}


def build_admin_user_payload(
    user: User,
    cookie_counts: dict[int, int] | None = None,
    balances: dict[int, str] | None = None,
) -> dict:
    """序列化用户及可选账号数、余额映射，返回包含北京时间创建、最后登录时间的数据。"""
    counts = cookie_counts or {}
    balance_map = balances or {}
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "role": user.role.value if user.role else None,
        "status": user.status.value if user.status else None,
        "is_admin": user.role == UserRole.ADMIN,
        "account_limit": user.account_limit,
        "cookie_count": counts.get(user.id, 0),
        "card_count": 0,
        "balance": _format_balance(balance_map.get(user.id)),
        "expire_at": safe_isoformat(user.expire_at),
        "created_at": safe_isoformat(user.created_at),
        "last_login_at": safe_isoformat(user.last_login_at),
    }


class AdminUserQueryService:
    """使用当前请求的数据库会话查询用户，列表与计数共用全部筛选条件。"""

    def __init__(self, session: AsyncSession):
        """接收当前请求会话，不创建额外引擎或连接池。"""
        self.session = session

    async def list(
        self, *, limit: int, offset: int, username: str | None, role: UserRole | None,
    ) -> dict:
        """按用户名和角色查询分页列表、总数与角色字典；参数均经ORM绑定。

        Args:
            limit: 当前页最大条数。
            offset: 分页偏移量。
            username: 可选用户名关键字，去除首尾空格后模糊匹配。
            role: 已校验的角色枚举或空值。
        Returns:
            用户列表、总条数、分页信息及数据库中的有效角色选项。
        """
        conditions = []
        username_keyword = username.strip() if username else ""
        if username_keyword:
            conditions.append(User.username.ilike(f"%{username_keyword}%"))
        if role is not None:
            conditions.append(User.role == role)

        total_stmt = select(func.count()).select_from(User).where(*conditions)
        total = (await self.session.execute(total_stmt)).scalar() or 0
        users_stmt = (
            select(User).where(*conditions)
            .order_by(User.created_at.desc(), User.id.desc()).limit(limit).offset(offset)
        )
        users = (await self.session.execute(users_stmt)).scalars().all()
        cookie_counts_stmt = select(XYAccount.owner_id, func.count()).group_by(XYAccount.owner_id)
        cookie_counts = dict((await self.session.execute(cookie_counts_stmt)).all())
        balances = await fetch_user_balances(self.session, [user.id for user in users])

        roles_stmt = select(XYDataDictionary.dict_value, XYDataDictionary.dict_label).where(
            XYDataDictionary.dict_type == USER_ROLE_DICTIONARY,
            XYDataDictionary.enabled.is_(True),
            XYDataDictionary.dict_value.in_([item.value for item in UserRole]),
        ).order_by(XYDataDictionary.sort_order, XYDataDictionary.id)
        roles = (await self.session.execute(roles_stmt)).all()
        return {
            "users": [build_admin_user_payload(user, cookie_counts, balances) for user in users],
            "total": total,
            "limit": limit,
            "offset": offset,
            "roles": [{"value": value, "label": label} for value, label in roles],
        }
