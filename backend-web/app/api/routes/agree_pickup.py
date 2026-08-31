"""
同意后发货 - 提货页公开接口（无需登录）

功能：
1. GET  /agree-pickup/order  ：校验订单并返回提货页展示信息
2. POST /agree-pickup/agree  ：买家点击「同意」触发真实发货并返回卡券内容

安全：
- 公开接口，须同时校验订单号(orderNo)与订单主键(orderId)匹配，二者皆对才放行；
  订单不存在 / 订单号与订单id不匹配 均返回明确中文提示。
- 触发发货全程 Redis 发货锁 + 幂等，防止并发重复发货（见 AgreePickupService）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.services.agree_pickup_service import AgreePickupService
from common.schemas.common import ApiResponse

router = APIRouter(tags=["同意后发货提货页"])


class AgreePickupAgreeRequest(BaseModel):
    """买家点击「同意」请求"""

    order_no: str
    order_id: str


@router.get("/order", response_model=ApiResponse)
async def query_pickup_order(
    orderNo: str = Query(default="", description="闲鱼订单号"),
    orderId: str = Query(default="", description="订单表主键ID"),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """提货页加载：校验订单并返回展示信息（含是否已同意/已同意时的发货内容）。"""
    success, message, data = await AgreePickupService(session).query_order(orderNo, orderId)
    return ApiResponse(success=success, message=message, data=data)


@router.post("/agree", response_model=ApiResponse)
async def agree_pickup(
    request: AgreePickupAgreeRequest,
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """买家点击「同意」：触发确认发货（免拼在前）并返回卡券内容。"""
    success, message, data = await AgreePickupService(session).agree(
        request.order_no, request.order_id
    )
    return ApiResponse(success=success, message=message, data=data)
