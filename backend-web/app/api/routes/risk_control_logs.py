"""
 风控日志查询路由。

 提供普通登录用户可访问的风控日志分页查询能力。
 管理员可查看全部数据，普通用户仅可查看自己的账号数据。
 """

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.services.risk_control_log_service import RiskControlLogService
from common.models.user import User
from common.utils.auth_scope import resolve_owner_scope

router = APIRouter(tags=["风控日志"])


@router.get("/risk-control-logs")
async def list_risk_logs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    cookie_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    processing_status: str | None = None,
    call_type: str | None = None,
    current_user: User = Depends(deps.get_current_active_user),
    risk_log_service: RiskControlLogService = Depends(deps.get_risk_log_service),
) -> dict:
    """分页查询风控日志，普通用户只返回自己的数据，管理员返回全部数据。"""
    try:
        owner_id, _ = resolve_owner_scope(current_user)
        items, total = await risk_log_service.list_logs(
            owner_id=owner_id,
            account_identifier=cookie_id,
            start_date=start_date,
            end_date=end_date,
            processing_status=processing_status,
            call_type=call_type,
            limit=limit,
            offset=offset,
        )
        return {"success": True, "data": items, "total": total, "limit": limit, "offset": offset}
    except Exception as exc:
        return {"success": False, "message": f"加载风控日志失败: {str(exc)}", "data": [], "total": 0, "limit": limit, "offset": offset}


@router.get("/risk-control-logs/today-success-rate")
async def get_today_success_rate(
    current_user: User = Depends(deps.get_current_active_user),
    risk_log_service: RiskControlLogService = Depends(deps.get_risk_log_service),
) -> dict:
    """查询当日（北京时间）风控处理成功率，普通用户只统计自己的数据，管理员统计全部数据。"""
    try:
        owner_id, _ = resolve_owner_scope(current_user)
        data = await risk_log_service.get_today_success_rate(owner_id=owner_id)
        return {"success": True, "data": data}
    except Exception as exc:
        return {"success": False, "message": f"加载当日成功率失败: {str(exc)}", "data": None}
