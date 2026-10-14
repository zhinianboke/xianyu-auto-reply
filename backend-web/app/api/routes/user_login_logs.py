"""
用户登录日志查询路由

功能：
1. 仅管理员可查询「用户登录日志」（返回全部用户的登录记录）
2. 支持按关键字、登录方式、时间范围筛选，后端分页
3. 与前端「日志管理 / 用户登录日志」页面对接
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from loguru import logger

from app.api import deps
from app.services.user_login_log_service import UserLoginLogService
from common.models.user import User

router = APIRouter(tags=["用户登录日志"])


@router.get("/user-login-logs")
async def list_user_login_logs(
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    keyword: str | None = Query(default=None, description="关键字（登录账号，或数字时按用户ID匹配）"),
    login_method: str | None = Query(
        default=None,
        description="登录方式 username_password/email_password/email_code",
    ),
    start_date: str | None = Query(default=None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期 YYYY-MM-DD"),
    _: User = Depends(deps.get_current_admin_user),
    service: UserLoginLogService = Depends(deps.get_user_login_log_service),
) -> dict:
    """分页查询用户登录日志（仅管理员，返回全部用户的记录）。

    返回统一结构：success/data/total/limit/offset，异常通过 success=False + message 返回。
    """
    try:
        items, total = await service.list_logs(
            keyword=keyword,
            login_method=login_method,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        return {"success": True, "data": items, "total": total, "limit": limit, "offset": offset}
    except Exception as exc:
        logger.error(
            "加载用户登录日志失败: "
            f"keyword={keyword}, login_method={login_method}, start_date={start_date}, "
            f"end_date={end_date}, limit={limit}, offset={offset}, "
            f"error={type(exc).__name__}: {exc}"
        )
        return {
            "success": False,
            "message": f"加载用户登录日志失败: {str(exc)}",
            "data": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        }