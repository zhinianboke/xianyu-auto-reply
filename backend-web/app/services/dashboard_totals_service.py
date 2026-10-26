"""管理员仪表盘和公开状态接口共用的全局用户、闲鱼账号总数查询。"""
from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.user import User
from common.models.xy_account import XYAccount


def build_dashboard_totals_statement() -> Select:
    """构建全局总数查询，保持管理员仪表盘统计全部用户和账号的口径。

    Returns:
        同一条 SQL 中统计用户与账号总数的语句，可追加账号聚合字段。
    """
    return select(
        select(func.count()).select_from(User).scalar_subquery().label("total_users"),
        func.count().label("total_accounts"),
    ).select_from(XYAccount)


async def get_dashboard_totals(session: AsyncSession) -> dict[str, int]:
    """只读取全局用户、账号总数，不读取任何用户或账号明细。

    Args:
        session: 由项目统一会话工厂提供的数据库会话。
    Returns:
        管理员仪表盘口径的 total_users 和 total_accounts。
    """
    row = (await session.execute(build_dashboard_totals_statement())).one()
    return {"total_users": int(row.total_users), "total_accounts": int(row.total_accounts)}
