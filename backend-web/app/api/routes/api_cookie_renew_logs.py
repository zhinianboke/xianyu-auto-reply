"""
接口续期Cookies日志路由模块

功能：
1. 提供接口续期Cookies批次列表查询接口（按日期范围、分页）
2. 提供接口续期Cookies批次详情查询接口（含批次汇总和该批次所有账号日志）
3. 提供清空10天前历史日志接口
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models.scheduled_api_cookie_renew_log import ScheduledApiCookieRenewLog
from common.models.xy_account import XYAccount
from common.models.user import User
from common.utils.time_utils import get_beijing_now_naive, safe_isoformat


router = APIRouter(tags=["接口续期Cookies日志"])


def _build_log_dict(log: ScheduledApiCookieRenewLog) -> dict:
    """构建单条日志的响应字典。"""
    return {
        "id": log.id,
        "batch_id": log.batch_id,
        "account_id": log.account_id,
        "status": log.status,
        "updated_cookie_count": log.updated_cookie_count,
        "updated_cookie_names": log.updated_cookie_names,
        "response_content": log.response_content,
        "error_message": log.error_message,
        "created_at": safe_isoformat(log.created_at),
    }


@router.get("/api-cookie-renew-batches")
async def list_api_cookie_renew_batches(
    start_date: str | None = Query(default=None, description="开始日期，格式：YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期，格式：YYYY-MM-DD"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取接口续期Cookies批次列表。"""
    base_query = select(
        ScheduledApiCookieRenewLog.batch_id,
        func.min(ScheduledApiCookieRenewLog.created_at).label("executed_at"),
        func.count().label("total_accounts"),
        func.sum(
            case((ScheduledApiCookieRenewLog.status == "success", 1), else_=0)
        ).label("success_count"),
        func.sum(
            case((ScheduledApiCookieRenewLog.status == "cookie_updated", 1), else_=0)
        ).label("cookie_updated_count"),
        func.sum(
            case((ScheduledApiCookieRenewLog.status == "browser_renewed", 1), else_=0)
        ).label("browser_renewed_count"),
        func.sum(
            case((ScheduledApiCookieRenewLog.status == "need_password_login", 1), else_=0)
        ).label("need_password_login_count"),
        func.sum(
            case((ScheduledApiCookieRenewLog.status == "failed", 1), else_=0)
        ).label("failed_count"),
    ).group_by(ScheduledApiCookieRenewLog.batch_id)

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            base_query = base_query.having(
                func.min(ScheduledApiCookieRenewLog.created_at) >= start_dt
            )
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
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
            base_query = base_query.having(
                func.min(ScheduledApiCookieRenewLog.created_at) <= end_dt
            )
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

    total = (
        await session.execute(select(func.count()).select_from(base_query.subquery()))
    ).scalar() or 0
    offset = (page - 1) * page_size
    stmt = (
        base_query.order_by(func.min(ScheduledApiCookieRenewLog.created_at).desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).all()

    batches = [
        {
            "batch_id": row.batch_id,
            "executed_at": safe_isoformat(row.executed_at),
            "total_accounts": row.total_accounts or 0,
            "success_count": row.success_count or 0,
            "cookie_updated_count": row.cookie_updated_count or 0,
            "browser_renewed_count": row.browser_renewed_count or 0,
            "need_password_login_count": row.need_password_login_count or 0,
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


@router.get("/api-cookie-renew-batches/{batch_id}")
async def get_api_cookie_renew_batch_detail(
    batch_id: str,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取接口续期Cookies批次详情。"""
    summary_stmt = select(
        func.min(ScheduledApiCookieRenewLog.created_at).label("executed_at"),
        func.count().label("total_accounts"),
        func.sum(
            case((ScheduledApiCookieRenewLog.status == "success", 1), else_=0)
        ).label("success_count"),
        func.sum(
            case((ScheduledApiCookieRenewLog.status == "cookie_updated", 1), else_=0)
        ).label("cookie_updated_count"),
        func.sum(
            case((ScheduledApiCookieRenewLog.status == "browser_renewed", 1), else_=0)
        ).label("browser_renewed_count"),
        func.sum(
            case((ScheduledApiCookieRenewLog.status == "need_password_login", 1), else_=0)
        ).label("need_password_login_count"),
        func.sum(
            case((ScheduledApiCookieRenewLog.status == "failed", 1), else_=0)
        ).label("failed_count"),
    ).where(ScheduledApiCookieRenewLog.batch_id == batch_id)
    summary = (await session.execute(summary_stmt)).first()

    if not summary or summary.total_accounts == 0:
        return {
            "success": False,
            "message": "批次不存在",
            "data": None,
        }

    logs_stmt = (
        select(ScheduledApiCookieRenewLog)
        .where(ScheduledApiCookieRenewLog.batch_id == batch_id)
        .order_by(ScheduledApiCookieRenewLog.created_at.asc())
    )
    logs = (await session.execute(logs_stmt)).scalars().all()

    # 查询所有相关账号的当前状态
    account_ids = list({log.account_id for log in logs if log.account_id})
    account_status_map: dict[str, str] = {}
    if account_ids:
        accounts_stmt = select(
            XYAccount.account_id, XYAccount.status
        ).where(XYAccount.account_id.in_(account_ids))
        account_rows = (await session.execute(accounts_stmt)).all()
        account_status_map = {row.account_id: row.status or "unknown" for row in account_rows}

    def _build_log_with_status(log: ScheduledApiCookieRenewLog) -> dict:
        d = _build_log_dict(log)
        d["account_status"] = account_status_map.get(log.account_id, "unknown")
        return d

    return {
        "success": True,
        "data": {
            "batch_id": batch_id,
            "executed_at": safe_isoformat(summary.executed_at),
            "total_accounts": summary.total_accounts or 0,
            "success_count": summary.success_count or 0,
            "cookie_updated_count": summary.cookie_updated_count or 0,
            "browser_renewed_count": summary.browser_renewed_count or 0,
            "need_password_login_count": summary.need_password_login_count or 0,
            "failed_count": summary.failed_count or 0,
            "logs": [_build_log_with_status(log) for log in logs],
        },
    }


@router.delete("/api-cookie-renew-logs/clear")
async def clear_api_cookie_renew_logs(
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """清空10天前的接口续期Cookies日志（保留最近10天）。"""
    try:
        ten_days_ago = get_beijing_now_naive() - timedelta(days=10)
        stmt = delete(ScheduledApiCookieRenewLog).where(
            ScheduledApiCookieRenewLog.created_at < ten_days_ago
        )
        result = await session.execute(stmt)
        await session.commit()
        deleted_count = result.rowcount or 0
        logger.info(
            f"[接口续期Cookies日志] 已清空 {deleted_count} 条 10 天前的日志"
        )
        return {
            "success": True,
            "message": f"已清空 {deleted_count} 条 10 天前的接口续期Cookies日志",
            "data": {"deleted_count": deleted_count},
        }
    except Exception as exc:
        await session.rollback()
        logger.error(f"[接口续期Cookies日志] 清空日志失败: {exc}")
        return {
            "success": False,
            "message": f"清空失败：{exc}",
            "data": None,
        }
