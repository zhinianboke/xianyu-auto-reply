from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.services.auto_reply_log_service import AutoReplyLogService
from common.models.user import User
from common.utils.auth_scope import resolve_owner_scope

router = APIRouter(tags=["消息回复日志"])


@router.get("/auto-reply-logs")
async def list_auto_reply_logs(
    account_id: str | None = Query(default=None, description="账号ID"),
    start_date: str | None = Query(default=None, description="开始日期，格式：YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期，格式：YYYY-MM-DD"),
    matched_rule_type: str | None = Query(default=None, description="规则类型筛选"),
    send_status: str | None = Query(default=None, description="发送状态：success-发送成功/failed-发送失败/unknown-待确认/timeout-超时"),
    message_type: str = Query(default="auto_reply", description="消息类型：auto_reply-自动回复/auto_delivery-自动发货"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    service = AutoReplyLogService(session)
    try:
        offset = (page - 1) * page_size
        owner_id, _ = resolve_owner_scope(current_user)
        items, total = await service.list_logs(
            owner_id=owner_id,
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            matched_rule_type=matched_rule_type,
            send_status=send_status,
            message_type=message_type,
            limit=page_size,
            offset=offset,
        )
    except ValueError as exc:
        return {
            "success": False,
            "message": str(exc),
            "data": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
        }

    return {
        "success": True,
        "message": "查询成功",
        "data": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }
