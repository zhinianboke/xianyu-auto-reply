"""
推广返佣系统 - 仪表盘API路由

功能：
1. 获取当前用户的统计概览（账号数、启用账号数等）
2. 管理员获取全局统计
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models.user import User, UserRole
from common.models.fy_account import FYAccount

router = APIRouter(tags=["仪表盘"])


@router.get("/stats")
async def get_dashboard_stats(
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """
    获取仪表盘统计数据

    普通用户：返回自己的账号统计
    管理员：返回全局统计
    """
    is_admin = current_user.role == UserRole.ADMIN

    # 账号统计
    account_query = select(
        func.count(FYAccount.id).label("total"),
        func.sum(case((FYAccount.enabled == True, 1), else_=0)).label("active"),
    )
    if not is_admin:
        account_query = account_query.where(FYAccount.owner_id == current_user.id)

    result = await session.execute(account_query)
    row = result.one()
    total_accounts = row.total or 0
    active_accounts = int(row.active or 0)

    # 管理员额外统计：用户数
    total_users = 0
    if is_admin:
        user_count_result = await session.execute(select(func.count(User.id)))
        total_users = user_count_result.scalar() or 0

    data = {
        "total_accounts": total_accounts,
        "active_accounts": active_accounts,
        "inactive_accounts": total_accounts - active_accounts,
    }

    if is_admin:
        data["total_users"] = total_users

    return {
        "success": True,
        "data": data,
    }
