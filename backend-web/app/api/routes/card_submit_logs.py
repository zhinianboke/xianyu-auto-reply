"""
卡密提交日志路由。

功能：
1. 仅管理员可分页查询卡密提交日志
2. 支持订单号、提交结果和时间区间筛选
3. 所有业务结果使用统一响应格式返回
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from loguru import logger

from app.api import deps
from app.services.card_submit_log_service import CardSubmitLogService
from common.models.user import User
from common.schemas.common import ApiResponse


router = APIRouter(tags=["卡密提交日志"])


@router.get("/card-submit-logs", response_model=ApiResponse)
async def list_card_submit_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    order_no: str | None = Query(default=None, description="订单号关键字"),
    submit_result: str | None = Query(default=None, description="提交结果：success/failure"),
    start_date: str | None = Query(default=None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期 YYYY-MM-DD"),
    _: User = Depends(deps.get_current_admin_user),
    service: CardSubmitLogService = Depends(deps.get_card_submit_log_service),
) -> ApiResponse:
    """管理员分页查询卡密提交日志。"""
    try:
        data = await service.list_logs(
            order_no=order_no,
            submit_result=submit_result,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )
        return ApiResponse(success=True, message="操作成功", data=data)
    except Exception as exc:
        logger.error(
            "加载卡密提交日志失败: "
            f"order_no={order_no}, submit_result={submit_result}, "
            f"start_date={start_date}, end_date={end_date}, page={page}, "
            f"page_size={page_size}, error={type(exc).__name__}: {exc}",
            exc_info=True,
        )
        return ApiResponse(
            success=False,
            code=40001,
            message=f"加载卡密提交日志失败: {exc}",
            data=None,
        )


@router.get("/card-submit-logs/options", response_model=ApiResponse)
async def get_card_submit_log_options(
    _: User = Depends(deps.get_current_admin_user),
    service: CardSubmitLogService = Depends(deps.get_card_submit_log_service),
) -> ApiResponse:
    """读取卡密提交日志筛选项。"""
    try:
        data = await service.get_options()
        return ApiResponse(success=True, message="操作成功", data=data)
    except Exception as exc:
        logger.error(
            f"加载卡密提交日志筛选项失败: {type(exc).__name__}: {exc}",
            exc_info=True,
        )
        return ApiResponse(
            success=False,
            code=40001,
            message=f"加载卡密提交日志筛选项失败: {exc}",
            data=None,
        )


__all__ = ["router"]
