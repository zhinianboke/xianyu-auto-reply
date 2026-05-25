"""
账号登录日志查询路由

功能：
1. 仅管理员可查询账号登录日志（所有账号的全部数据）
2. 支持按账号、时间范围、登录状态筛选
3. 与前端「日志管理 / 账号登录日志」页面对接
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.services.account_login_log_service import AccountLoginLogService
from common.models.user import User

router = APIRouter(tags=["账号登录日志"])


@router.get("/account-login-logs")
async def list_account_login_logs(
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    cookie_id: str | None = Query(default=None, description="按账号ID筛选"),
    start_date: str | None = Query(default=None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期 YYYY-MM-DD"),
    login_status: str | None = Query(default=None, description="登录状态 success/failed/skipped_cooldown/no_credentials"),
    _: User = Depends(deps.get_current_admin_user),
    login_log_service: AccountLoginLogService = Depends(deps.get_account_login_log_service),
) -> dict:
    """分页查询账号登录日志（仅管理员，返回所有账号的全部数据）

    返回统一结构：success/data/total/limit/offset，异常通过 success=False + message 返回。
    """
    try:
        items, total = await login_log_service.list_logs(
            owner_id=None,  # 管理员查全部
            account_identifier=cookie_id,
            start_date=start_date,
            end_date=end_date,
            login_status=login_status,
            limit=limit,
            offset=offset,
        )
        return {"success": True, "data": items, "total": total, "limit": limit, "offset": offset}
    except Exception as exc:
        return {
            "success": False,
            "message": f"加载账号登录日志失败: {str(exc)}",
            "data": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        }
