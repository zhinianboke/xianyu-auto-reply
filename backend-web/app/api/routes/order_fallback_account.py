"""
用户级兜底下单账号配置接口

功能：
1. 查询当前用户的兜底下单账号配置
2. 保存（新增/更新）当前用户的兜底下单账号配置
3. 多用户数据隔离：每个用户仅一条配置，按 owner_id 隔离

说明：当定时下单任务发现监控任务自身无可用下单账号（任务删除/禁用/未配置/账号失效）时，
回退使用此处配置的兜底账号下单。
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db_session
from common.models.user import User
from common.schemas.common import ApiResponse
from common.services.order_fallback_account_service import OrderFallbackAccountService

router = APIRouter(prefix="/product-monitor/order-fallback-accounts", tags=["兜底下单账号"])


class OrderFallbackAccountSaveRequest(BaseModel):
    """保存兜底下单账号配置请求"""

    account_ids: List[str] = Field(default_factory=list, description="兜底下单账号ID列表（可多选，可为空表示不配置）")


def _resolve_owner_id(current_user: User) -> int:
    """兜底配置为用户级数据：管理员同样按自身ID存储，保证每用户一条。"""
    return current_user.id


@router.get("", response_model=ApiResponse)
async def get_order_fallback_accounts(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """查询当前用户的兜底下单账号配置"""
    svc = OrderFallbackAccountService(session)
    data = await svc.get_config(_resolve_owner_id(current_user))
    return ApiResponse(success=True, message="查询成功", data=data)


@router.put("", response_model=ApiResponse)
async def save_order_fallback_accounts(
    req: OrderFallbackAccountSaveRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """保存（新增/更新）当前用户的兜底下单账号配置"""
    svc = OrderFallbackAccountService(session)
    try:
        data = await svc.save_config(_resolve_owner_id(current_user), req.account_ids)
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    return ApiResponse(success=True, message="兜底下单账号保存成功", data=data)
