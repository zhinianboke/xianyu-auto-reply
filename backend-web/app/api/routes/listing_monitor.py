"""
商品上新监控任务接口

功能：
1. 提供上新监控任务的分页查询
2. 提供新建、编辑、启停、批量删除监控任务能力
3. 多用户数据隔离：普通用户仅能管理本人任务，管理员可管理全部
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db_session
from app.services.listing_monitor_service import ListingMonitorService, _task_to_dict
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.auth_scope import resolve_owner_scope

router = APIRouter(prefix="/product-monitor/listing-tasks", tags=["商品上新监控"])


class ListingMonitorCreateRequest(BaseModel):
    """创建上新监控任务请求"""

    monitor_type: str = Field(..., description="监控类型：listing-上新监控，price_drop-降价监控")
    keyword: str = Field(..., min_length=1, max_length=200, description="商品监控关键字")
    price_min: Optional[float] = Field(None, ge=0, description="商品价格区间最低值")
    price_max: Optional[float] = Field(None, ge=0, description="商品价格区间最高值")
    interval_minutes: int = Field(..., ge=1, description="任务执行间隔（分钟）")
    collect_pages: int = Field(1, ge=1, description="每次采集页数")
    account_ids: List[str] = Field(..., min_length=1, description="关联的闲鱼账号ID列表（至少一个）")
    dm_account_id: Optional[str] = Field(None, description="私信账号ID（单选，非必填）")
    dm_content: Optional[str] = Field(None, max_length=1000, description="私信内容（填写私信账号后必填）")
    order_account_id: Optional[str] = Field(None, description="下单账号ID（单选，非必填）")
    is_enabled: bool = Field(True, description="是否启用")
    remark: Optional[str] = Field(None, max_length=500, description="备注")


class ListingMonitorUpdateRequest(BaseModel):
    """更新上新监控任务请求"""

    monitor_type: Optional[str] = Field(None, description="监控类型：listing-上新监控，price_drop-降价监控")
    keyword: Optional[str] = Field(None, min_length=1, max_length=200)
    price_min: Optional[float] = Field(None, ge=0)
    price_max: Optional[float] = Field(None, ge=0)
    interval_minutes: Optional[int] = Field(None, ge=1)
    collect_pages: Optional[int] = Field(None, ge=1)
    account_ids: Optional[List[str]] = Field(None)
    dm_account_id: Optional[str] = Field(None, description="私信账号ID（单选，非必填）")
    dm_content: Optional[str] = Field(None, max_length=1000, description="私信内容（填写私信账号后必填）")
    order_account_id: Optional[str] = Field(None, description="下单账号ID（单选，非必填）")
    is_enabled: Optional[bool] = Field(None)
    remark: Optional[str] = Field(None, max_length=500)


class ListingMonitorStatusUpdateRequest(BaseModel):
    """更新上新监控任务启停状态请求"""

    is_enabled: bool = Field(..., description="是否启用")


class ListingMonitorBatchDeleteRequest(BaseModel):
    """批量删除上新监控任务请求"""

    ids: List[int] = Field(default_factory=list, description="监控任务ID列表")


@router.get("", response_model=ApiResponse)
async def list_listing_monitor_tasks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, description="每页条数"),
    keyword: Optional[str] = Query(None, description="按关键字筛选"),
    is_enabled: Optional[bool] = Query(None, description="是否启用"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """分页查询上新监控任务列表"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    data = await svc.list_tasks(
        owner_id=owner_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        is_enabled=is_enabled,
    )
    return ApiResponse(success=True, message="查询成功", data=data)


@router.post("", response_model=ApiResponse)
async def create_listing_monitor_task(
    req: ListingMonitorCreateRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """创建上新监控任务"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    try:
        task = await svc.create(owner_id, current_user.id, req.model_dump())
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    return ApiResponse(success=True, message="监控任务创建成功", data={"task": _task_to_dict(task)})


@router.put("/{task_id}", response_model=ApiResponse)
async def update_listing_monitor_task(
    task_id: int,
    req: ListingMonitorUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """更新上新监控任务"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    try:
        updated = await svc.update(owner_id, task_id, req.model_dump(exclude_unset=True))
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    if not updated:
        return ApiResponse(success=False, message="监控任务不存在")
    return ApiResponse(success=True, message="监控任务更新成功", data={"task": _task_to_dict(updated)})


@router.put("/{task_id}/status", response_model=ApiResponse)
async def update_listing_monitor_task_status(
    task_id: int,
    req: ListingMonitorStatusUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """启用/停用上新监控任务"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    updated = await svc.update_status(owner_id, task_id, req.is_enabled)
    if not updated:
        return ApiResponse(success=False, message="监控任务不存在")
    return ApiResponse(success=True, message="监控任务状态更新成功", data={"task": _task_to_dict(updated)})


@router.post("/batch-delete", response_model=ApiResponse)
async def batch_delete_listing_monitor_tasks(
    req: ListingMonitorBatchDeleteRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """批量删除上新监控任务"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    try:
        success_count = await svc.batch_delete(owner_id, req.ids)
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    return ApiResponse(
        success=True,
        message=f"成功删除 {success_count} 条监控任务",
        data={"success_count": success_count, "total_count": len(req.ids)},
    )


@router.get("/options", response_model=ApiResponse)
async def list_listing_monitor_task_options(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """查询监控任务下拉选项（用于日志/采集商品页按任务筛选）"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    data = await svc.list_task_options(owner_id)
    return ApiResponse(success=True, message="查询成功", data={"list": data})


@router.get("/logs", response_model=ApiResponse)
async def list_listing_monitor_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, description="每页条数"),
    monitor_task_id: Optional[int] = Query(None, description="按监控任务筛选"),
    status: Optional[str] = Query(None, description="按执行状态筛选：success/partial/failed"),
    monitor_type: Optional[str] = Query(None, description="按监控类型筛选：listing/price_drop"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """分页查询监控执行日志"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    data = await svc.list_logs(
        owner_id=owner_id,
        page=page,
        page_size=page_size,
        monitor_task_id=monitor_task_id,
        status=status,
        monitor_type=monitor_type,
    )
    return ApiResponse(success=True, message="查询成功", data=data)


@router.get("/items", response_model=ApiResponse)
async def list_listing_monitor_items(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, description="每页条数"),
    monitor_task_id: Optional[int] = Query(None, description="按监控任务筛选"),
    keyword: Optional[str] = Query(None, description="按商品标题筛选"),
    area: Optional[str] = Query(None, description="按地区筛选"),
    seller_nick: Optional[str] = Query(None, description="按卖家昵称筛选"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """分页查询采集商品信息"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    data = await svc.list_items(
        owner_id=owner_id,
        page=page,
        page_size=page_size,
        monitor_task_id=monitor_task_id,
        keyword=keyword,
        area=area,
        seller_nick=seller_nick,
    )
    return ApiResponse(success=True, message="查询成功", data=data)
