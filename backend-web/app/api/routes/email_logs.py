"""
邮件发送日志查询路由

功能：
1. 仅管理员可查询邮件发送日志
2. 支持邮箱关键字、触发操作、发送结果、时间区间筛选
3. 后端分页，前端支持指定页跳转
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from loguru import logger

from app.api import deps
from app.services.email_log_service import EmailLogService
from common.models.user import User
from common.schemas.common import ApiResponse

router = APIRouter(tags=["邮件日志"])


@router.get("/email-logs", response_model=ApiResponse)
async def list_email_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    recipient_email: str | None = Query(default=None, description="收件邮箱关键字"),
    trigger_operation: str | None = Query(default=None, description="触发操作"),
    send_result: str | None = Query(default=None, description="发送结果：success/failure"),
    start_date: str | None = Query(default=None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期 YYYY-MM-DD"),
    _: User = Depends(deps.get_current_admin_user),
    service: EmailLogService = Depends(deps.get_email_log_service),
) -> ApiResponse:
    """管理员分页查询邮件发送日志。"""
    try:
        data = await service.list_logs(
            recipient_email=recipient_email,
            trigger_operation=trigger_operation,
            send_result=send_result,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )
        return ApiResponse(success=True, message="操作成功", data=data)
    except Exception as exc:
        logger.error(
            "加载邮件发送日志失败: "
            f"recipient_email={recipient_email}, trigger_operation={trigger_operation}, "
            f"send_result={send_result}, start_date={start_date}, end_date={end_date}, "
            f"page={page}, page_size={page_size}, error={type(exc).__name__}: {exc}",
            exc_info=True,
        )
        return ApiResponse(success=False, code=40001, message=f"加载邮件发送日志失败: {exc}", data=None)


@router.get("/email-logs/options", response_model=ApiResponse)
async def get_email_log_options(
    _: User = Depends(deps.get_current_admin_user),
    service: EmailLogService = Depends(deps.get_email_log_service),
) -> ApiResponse:
    """读取邮件日志筛选枚举。"""
    try:
        data = await service.get_options()
        return ApiResponse(success=True, message="操作成功", data=data)
    except Exception as exc:
        logger.error(f"加载邮件日志筛选项失败: {type(exc).__name__}: {exc}", exc_info=True)
        return ApiResponse(success=False, code=40001, message=f"加载邮件日志筛选项失败: {exc}", data=None)


__all__ = ["router"]
