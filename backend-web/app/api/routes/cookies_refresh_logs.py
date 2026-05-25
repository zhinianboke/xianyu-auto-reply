"""
COOKIES刷新日志路由模块

功能：
1. 提供COOKIES刷新批次列表查询接口
2. 提供COOKIES刷新批次详情查询接口
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models.scheduled_cookies_refresh_log import ScheduledCookiesRefreshLog
from common.models.user import User

from common.utils.time_utils import safe_isoformat
router = APIRouter(tags=["COOKIES刷新日志"])


@router.get("/cookies-refresh-batches")
async def list_cookies_refresh_batches(
    start_date: str | None = Query(default=None, description="开始日期，格式：YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期，格式：YYYY-MM-DD"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取COOKIES刷新执行批次列表。"""
    from datetime import datetime

    base_query = select(
        ScheduledCookiesRefreshLog.batch_id,
        func.min(ScheduledCookiesRefreshLog.created_at).label("executed_at"),
        func.count().label("total_accounts"),
        func.sum(case((ScheduledCookiesRefreshLog.status == "initialized", 1), else_=0)).label("initialized_count"),
        func.sum(case((ScheduledCookiesRefreshLog.status == "success", 1), else_=0)).label("success_count"),
        func.sum(case((ScheduledCookiesRefreshLog.status == "failed", 1), else_=0)).label("failed_count"),
    ).group_by(ScheduledCookiesRefreshLog.batch_id)

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            base_query = base_query.having(func.min(ScheduledCookiesRefreshLog.created_at) >= start_dt)
        except ValueError:
            return {
                "success": False,
                "message": "开始日期格式错误，应为 YYYY-MM-DD",
                "data": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
            }

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            base_query = base_query.having(func.min(ScheduledCookiesRefreshLog.created_at) <= end_dt)
        except ValueError:
            return {
                "success": False,
                "message": "结束日期格式错误，应为 YYYY-MM-DD",
                "data": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
            }

    total = (await session.execute(select(func.count()).select_from(base_query.subquery()))).scalar() or 0
    offset = (page - 1) * page_size
    stmt = base_query.order_by(func.min(ScheduledCookiesRefreshLog.created_at).desc()).offset(offset).limit(page_size)
    rows = (await session.execute(stmt)).all()

    batches = [
        {
            "batch_id": row.batch_id,
            "executed_at": safe_isoformat(row.executed_at),
            "total_accounts": row.total_accounts or 0,
            "initialized_count": row.initialized_count or 0,
            "success_count": row.success_count or 0,
            "failed_count": row.failed_count or 0,
        }
        for row in rows
    ]

    return {
        "success": True,
        "data": batches,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/cookies-refresh-batches/{batch_id}")
async def get_cookies_refresh_batch_detail(
    batch_id: str,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取COOKIES刷新批次详情。"""
    summary_stmt = select(
        func.min(ScheduledCookiesRefreshLog.created_at).label("executed_at"),
        func.count().label("total_accounts"),
        func.sum(case((ScheduledCookiesRefreshLog.status == "initialized", 1), else_=0)).label("initialized_count"),
        func.sum(case((ScheduledCookiesRefreshLog.status == "success", 1), else_=0)).label("success_count"),
        func.sum(case((ScheduledCookiesRefreshLog.status == "failed", 1), else_=0)).label("failed_count"),
    ).where(ScheduledCookiesRefreshLog.batch_id == batch_id)
    summary = (await session.execute(summary_stmt)).first()

    if not summary or summary.total_accounts == 0:
        return {
            "success": False,
            "message": "批次不存在",
            "data": None,
        }

    logs_stmt = select(ScheduledCookiesRefreshLog).where(
        ScheduledCookiesRefreshLog.batch_id == batch_id
    ).order_by(ScheduledCookiesRefreshLog.created_at.asc())
    logs = (await session.execute(logs_stmt)).scalars().all()

    return {
        "success": True,
        "data": {
            "batch_id": batch_id,
            "executed_at": safe_isoformat(summary.executed_at),
            "total_accounts": summary.total_accounts or 0,
            "initialized_count": summary.initialized_count or 0,
            "success_count": summary.success_count or 0,
            "failed_count": summary.failed_count or 0,
            "logs": [
                {
                    "id": log.id,
                    "batch_id": log.batch_id,
                    "account_id": log.account_id,
                    "status": log.status,
                    "updated_cookie_count": log.updated_cookie_count,
                    "next_expire_at": safe_isoformat(log.next_expire_at),
                    "error_message": log.error_message,
                    "created_at": safe_isoformat(log.created_at),
                }
                for log in logs
            ],
        },
    }
