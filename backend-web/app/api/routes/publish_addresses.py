"""
商品发布随机地址池接口

功能：
1. 提供随机地址池分页查询与账号选项查询
2. 提供管理员新增、编辑、启停随机地址能力
3. 为普通用户提供只读查看能力
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_current_admin_user, get_db_session
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.auth_scope import resolve_owner_scope
from app.services.publish_address_service import PublishAddressService, _address_to_dict

router = APIRouter(prefix="/product-publish/addresses", tags=["商品发布随机地址池"])


class PublishAddressCreateRequest(BaseModel):
    """创建随机地址请求"""

    address: str = Field(..., min_length=1, max_length=200, description="地址文本")


class PublishAddressUpdateRequest(BaseModel):
    """更新随机地址请求"""

    address: Optional[str] = Field(None, min_length=1, max_length=200)


class PublishAddressBatchDeleteRequest(BaseModel):
    """批量删除随机地址请求"""

    ids: List[int] = Field(default_factory=list, description="随机地址ID列表")


class PublishAddressStatusUpdateRequest(BaseModel):
    """更新随机地址启停状态请求"""

    is_enabled: bool = Field(..., description="是否启用")


@router.get("", response_model=ApiResponse)
async def list_publish_addresses(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, description="每页条数"),
    keyword: Optional[str] = Query(None, description="关键词"),
    account_id: Optional[str] = Query(None, description="账号ID，__global__ 表示仅看全局地址"),
    is_enabled: Optional[bool] = Query(None, description="是否启用"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """分页查询随机地址池"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = PublishAddressService(session)
    data = await svc.list_addresses(
        owner_id=owner_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        account_id=account_id,
        is_enabled=is_enabled,
    )
    return ApiResponse(success=True, message="查询成功", data=data)


@router.get("/account-options", response_model=ApiResponse)
async def list_publish_address_account_options(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """查询随机地址池可选账号列表"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = PublishAddressService(session)
    data = await svc.list_account_options(owner_id=owner_id)
    return ApiResponse(success=True, message="查询成功", data={"list": data})


@router.post("", response_model=ApiResponse)
async def create_publish_address(
    req: PublishAddressCreateRequest,
    current_user: User = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """创建随机地址"""
    svc = PublishAddressService(session)
    try:
        address = await svc.create(current_user.id, req.model_dump())
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    return ApiResponse(success=True, message="随机地址创建成功", data={"address": _address_to_dict(address)})


@router.put("/{address_id}", response_model=ApiResponse)
async def update_publish_address(
    address_id: int,
    req: PublishAddressUpdateRequest,
    current_user: User = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """更新随机地址"""
    svc = PublishAddressService(session)
    try:
        updated = await svc.update(address_id, req.model_dump(exclude_unset=True))
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    if not updated:
        return ApiResponse(success=False, message="随机地址不存在")
    return ApiResponse(success=True, message="随机地址更新成功", data={"address": _address_to_dict(updated)})


@router.post("/batch-delete", response_model=ApiResponse)
async def batch_delete_publish_addresses(
    req: PublishAddressBatchDeleteRequest,
    current_user: User = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """批量删除随机地址"""
    svc = PublishAddressService(session)
    try:
        success_count = await svc.batch_delete(req.ids)
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))

    return ApiResponse(
        success=True,
        message=f"成功删除 {success_count} 条随机地址",
        data={"success_count": success_count, "total_count": len(req.ids)},
    )


@router.put("/{address_id}/status", response_model=ApiResponse)
async def update_publish_address_status(
    address_id: int,
    req: PublishAddressStatusUpdateRequest,
    current_user: User = Depends(get_current_admin_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """更新随机地址启停状态"""
    svc = PublishAddressService(session)
    updated = await svc.update_status(address_id, req.is_enabled)
    if not updated:
        return ApiResponse(success=False, message="随机地址不存在")
    return ApiResponse(
        success=True,
        message="随机地址状态更新成功",
        data={"address": _address_to_dict(updated)},
    )
