"""
Token 续期日志路由模块。

功能：
1. 提供 Token 续期批次列表分页查询接口。
2. 提供 Token 续期批次明细查询接口。
3. 统一返回业务响应格式，并限制为管理员访问。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.services.scheduled_batch_log_service import ScheduledBatchLogService
from common.models.user import User


router = APIRouter(tags=["Token续期日志"])


def _invalid_date_message(value: str | None, label: str) -> str | None:
    """校验查询日期并返回中文错误信息。"""
    if not value:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return f"{label}格式错误，应为 YYYY-MM-DD"
    return None


@router.get("/token-renewal-batches")
async def list_token_renewal_batches(
    start_date: str | None = Query(default=None, description="开始日期，格式：YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期，格式：YYYY-MM-DD"),
    page: str = Query(default="1", description="页码"),
    page_size: str = Query(default="20", description="每页数量"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取 Token 续期执行批次列表。"""
    try:
        page_number = int(page)
        page_size_number = int(page_size)
    except ValueError:
        page_number = 0
        page_size_number = 0
    if page_number < 1 or page_size_number not in {10, 20, 50, 100}:
        return {
            "success": False,
            "code": 40002,
            "message": "分页参数错误，每页数量仅支持 10、20、50、100",
            "data": None,
        }

    date_error = _invalid_date_message(start_date, "开始日期") or _invalid_date_message(
        end_date,
        "结束日期",
    )
    if date_error:
        return {
            "success": False,
            "code": 40001,
            "message": date_error,
            "data": None,
        }

    service = ScheduledBatchLogService(session)
    items, total = await service.list_token_renewal_batches(
        start_date=start_date,
        end_date=end_date,
        page=page_number,
        page_size=page_size_number,
    )
    return {
        "success": True,
        "code": 200,
        "message": "查询成功",
        "data": {
            "items": items,
            "total": total,
            "page": page_number,
            "page_size": page_size_number,
            "total_pages": (
                (total + page_size_number - 1) // page_size_number if total else 0
            ),
        },
    }


@router.get("/token-renewal-batches/{batch_id}")
async def get_token_renewal_batch_detail(
    batch_id: str,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取指定 Token 续期批次的逐账号明细。"""
    detail = await ScheduledBatchLogService(session).get_token_renewal_batch_detail(
        batch_id
    )
    if detail is None:
        return {
            "success": False,
            "code": 40401,
            "message": "Token续期批次不存在",
            "data": None,
        }
    return {
        "success": True,
        "code": 200,
        "message": "查询成功",
        "data": detail,
    }
