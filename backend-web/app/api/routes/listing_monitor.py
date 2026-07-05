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
from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.services.listing_monitor_service import ListingMonitorService, _task_to_dict
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.auth_scope import resolve_owner_scope

router = APIRouter(prefix="/product-monitor/listing-tasks", tags=["商品上新监控"])


class ListingMonitorCreateRequest(BaseModel):
    """创建上新监控任务请求"""

    monitor_type: str = Field(..., description="监控类型：listing-上新监控，price_drop-降价监控")
    category_id: int = Field(..., description="所属分类ID（必填）")
    keyword: str = Field(..., min_length=1, max_length=200, description="商品监控关键字")
    price_min: Optional[float] = Field(None, ge=0, description="商品价格区间最低值")
    price_max: Optional[float] = Field(None, ge=0, description="商品价格区间最高值")
    publish_days: Optional[int] = Field(None, ge=1, le=365, description="上新天数筛选（publishDays，单位天，留空=不限）")
    interval_minutes: int = Field(..., ge=1, description="任务执行间隔（分钟）")
    collect_pages: int = Field(1, ge=1, description="每次采集页数")
    proxy_url: Optional[str] = Field(None, max_length=255, description="代理API地址（GET返回IP:PORT列表，空=不使用代理）")
    account_ids: List[str] = Field(default_factory=list, description="采集账号ID列表（多选，非必填；不可用时回退兜底）")
    order_account_ids: Optional[List[str]] = Field(None, description="下单账号ID列表（多选，私信与下单共用，非必填）")
    dm_content: Optional[str] = Field(None, max_length=1000, description="私信内容（配置下单账号后必填）")
    dm_batch_size: int = Field(5, ge=1, le=100, description="每次定时私信任务最多处理条数")
    order_batch_size: int = Field(5, ge=1, le=100, description="每次定时下单任务最多处理条数")
    direct_order: bool = Field(False, description="采集后是否直接下单（开启则新采集商品立即用下单账号下单后再入库）")
    is_enabled: bool = Field(True, description="是否启用")
    remark: Optional[str] = Field(None, max_length=500, description="备注")


class ListingMonitorUpdateRequest(BaseModel):
    """更新上新监控任务请求"""

    monitor_type: Optional[str] = Field(None, description="监控类型：listing-上新监控，price_drop-降价监控")
    category_id: Optional[int] = Field(None, description="所属分类ID")
    keyword: Optional[str] = Field(None, min_length=1, max_length=200)
    price_min: Optional[float] = Field(None, ge=0)
    price_max: Optional[float] = Field(None, ge=0)
    publish_days: Optional[int] = Field(None, ge=1, le=365, description="上新天数筛选（publishDays，单位天，留空=不限）")
    interval_minutes: Optional[int] = Field(None, ge=1)
    collect_pages: Optional[int] = Field(None, ge=1)
    proxy_url: Optional[str] = Field(None, max_length=255, description="代理API地址（GET返回IP:PORT列表，空=不使用代理）")
    account_ids: Optional[List[str]] = Field(None)
    order_account_ids: Optional[List[str]] = Field(None, description="下单账号ID列表（多选，私信与下单共用，非必填）")
    dm_content: Optional[str] = Field(None, max_length=1000, description="私信内容（配置下单账号后必填）")
    dm_batch_size: Optional[int] = Field(None, ge=1, le=100, description="每次定时私信任务最多处理条数")
    order_batch_size: Optional[int] = Field(None, ge=1, le=100, description="每次定时下单任务最多处理条数")
    direct_order: Optional[bool] = Field(None, description="采集后是否直接下单")
    is_enabled: Optional[bool] = Field(None)
    remark: Optional[str] = Field(None, max_length=500)


class ListingMonitorStatusUpdateRequest(BaseModel):
    """更新上新监控任务启停状态请求"""

    is_enabled: bool = Field(..., description="是否启用")


class ListingMonitorBatchDeleteRequest(BaseModel):
    """批量删除上新监控任务请求"""

    ids: List[int] = Field(default_factory=list, description="监控任务ID列表")


class ListingMonitorBatchAccountsRequest(BaseModel):
    """批量修改上新监控任务账号请求"""

    ids: List[int] = Field(default_factory=list, description="监控任务ID列表")
    field: str = Field(..., description="要修改的账号字段：account_ids-采集账号，order_account_ids-下单账号")
    account_ids: List[str] = Field(default_factory=list, description="选择的账号ID列表")


class ListingMonitorBatchCategoryRequest(BaseModel):
    """批量修改上新监控任务分类请求"""

    ids: List[int] = Field(default_factory=list, description="监控任务ID列表")
    category_id: int = Field(..., description="目标分类ID（必填）")


class ListingMonitorBatchDmContentRequest(BaseModel):
    """批量修改上新监控任务私信内容请求"""

    ids: List[int] = Field(default_factory=list, description="监控任务ID列表")
    dm_content: str = Field(..., min_length=1, max_length=1000, description="私信内容（必填）")


class ListingMonitorCopyCookiesRequest(BaseModel):
    """复制监控日志账号Cookies请求"""

    ids: List[int] = Field(default_factory=list, description="监控日志ID列表")


class ListingMonitorResetItemsDmRequest(BaseModel):
    """批量重置采集商品私信失败状态请求"""

    ids: List[int] = Field(default_factory=list, description="采集商品主键ID列表")


@router.get("", response_model=ApiResponse)
async def list_listing_monitor_tasks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, description="每页条数"),
    keyword: Optional[str] = Query(None, description="按关键字筛选"),
    is_enabled: Optional[bool] = Query(None, description="是否启用"),
    category_id: Optional[int] = Query(None, description="按分类筛选"),
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
        category_id=category_id,
    )
    return ApiResponse(success=True, message="查询成功", data=data)


@router.get("/overview", response_model=ApiResponse)
async def listing_monitor_overview(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """商品监控总览统计（任务数、今日执行成功/失败、今日采集/私信/下单数等，按用户隔离）"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    data = await svc.get_overview(owner_id)
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


@router.post("/{task_id}/run", response_model=ApiResponse)
async def run_listing_monitor_task(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """手动执行单个商品监控任务采集（立即执行一次，忽略间隔，日志记为手动触发）"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    task = await svc.get(owner_id, task_id)
    if not task:
        return ApiResponse(success=False, message="监控任务不存在")
    if not task.is_enabled:
        return ApiResponse(success=False, message="任务已停用，请先启用后再手动采集")

    settings = get_settings()
    http_client = get_http_client()
    url = f"{settings.scheduler_service_url}/internal/tasks/listing_monitor/run/{task_id}"
    try:
        resp = await http_client.post(url)
    except Exception as exc:  # noqa: BLE001
        return ApiResponse(success=False, message=f"调用采集服务失败：{exc}")
    if not isinstance(resp, dict) or not resp.get("success"):
        msg = resp.get("message") if isinstance(resp, dict) else None
        return ApiResponse(success=False, message=msg or "采集执行失败")
    return ApiResponse(success=True, message=resp.get("message") or "采集已执行")


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


@router.post("/batch-update-accounts", response_model=ApiResponse)
async def batch_update_listing_monitor_accounts(
    req: ListingMonitorBatchAccountsRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """批量修改监控任务的监控账号或下单账号"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    try:
        success_count = await svc.batch_update_accounts(owner_id, req.ids, req.field, req.account_ids)
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    field_label = "采集账号" if req.field == "account_ids" else "下单账号"
    return ApiResponse(
        success=True,
        message=f"成功为 {success_count} 条监控任务修改{field_label}",
        data={"success_count": success_count, "total_count": len(req.ids)},
    )


@router.post("/batch-update-category", response_model=ApiResponse)
async def batch_update_listing_monitor_category(
    req: ListingMonitorBatchCategoryRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """批量修改监控任务的所属分类"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    try:
        success_count = await svc.batch_update_category(owner_id, req.ids, req.category_id)
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    return ApiResponse(
        success=True,
        message=f"成功为 {success_count} 条监控任务修改分类",
        data={"success_count": success_count, "total_count": len(req.ids)},
    )


@router.post("/batch-update-dm-content", response_model=ApiResponse)
async def batch_update_listing_monitor_dm_content(
    req: ListingMonitorBatchDmContentRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """批量修改监控任务的私信内容"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    try:
        success_count = await svc.batch_update_dm_content(owner_id, req.ids, req.dm_content)
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    return ApiResponse(
        success=True,
        message=f"成功为 {success_count} 条监控任务修改私信内容",
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


@router.delete("/logs/clear", response_model=ApiResponse)
async def clear_listing_monitor_logs(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """清空监控日志（只清空10天前的数据，保留最近10天）"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    try:
        data = await svc.clear_logs(owner_id)
        deleted_count = data.get("deleted_count", 0)
        return ApiResponse(
            success=True,
            message=f"已清空 {deleted_count} 条10天前的监控日志",
            data=data,
        )
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        return ApiResponse(success=False, message=f"清空监控日志失败: {exc}")


@router.post("/logs/copy-cookies", response_model=ApiResponse)
async def copy_listing_monitor_log_cookies(
    req: ListingMonitorCopyCookiesRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """汇总选中监控日志涉及的账号（去重），返回账号ID/Cookie/分销秘钥，供前端复制为JSON"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    try:
        data = await svc.collect_log_account_cookies(owner_id, req.ids)
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    return ApiResponse(success=True, message="查询成功", data={"list": data})


@router.get("/items", response_model=ApiResponse)
async def list_listing_monitor_items(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, description="每页条数"),
    monitor_task_id: Optional[int] = Query(None, description="按监控任务筛选"),
    keyword: Optional[str] = Query(None, description="按商品标题筛选"),
    area: Optional[str] = Query(None, description="按地区筛选"),
    seller_nick: Optional[str] = Query(None, description="按卖家昵称筛选"),
    item_id: Optional[str] = Query(None, description="按商品ID精确筛选"),
    is_dm_sent: Optional[bool] = Query(None, description="是否已私信"),
    is_ordered: Optional[bool] = Query(None, description="是否已下单"),
    seller_fill: Optional[str] = Query(None, description="卖家补全状态：filled/pending/failed"),
    has_detail: Optional[bool] = Query(None, description="是否已获取详情"),
    dm_state: Optional[str] = Query(None, description="私信状态：not_sent/waiting/pending/success/failed"),
    order_state: Optional[str] = Query(None, description="下单状态：not_ordered/ordered/failed/no_account/duplicate"),
    created_start: Optional[str] = Query(None, description="采集时间区间开始（北京时间，如 2026-06-18T00:00）"),
    created_end: Optional[str] = Query(None, description="采集时间区间结束（北京时间，如 2026-06-18T23:59）"),
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
        item_id=item_id,
        is_dm_sent=is_dm_sent,
        is_ordered=is_ordered,
        seller_fill=seller_fill,
        has_detail=has_detail,
        dm_state=dm_state,
        order_state=order_state,
        created_start=created_start,
        created_end=created_end,
    )
    return ApiResponse(success=True, message="查询成功", data=data)


@router.post("/items/reset-dm", response_model=ApiResponse)
async def reset_listing_monitor_items_dm(
    req: ListingMonitorResetItemsDmRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """批量将选中的"私信失败"采集商品重置为"未私信"，等待定时任务重试"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    try:
        success_count = await svc.reset_items_dm_failed(owner_id, req.ids)
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    return ApiResponse(
        success=True,
        message=f"成功重置 {success_count} 条私信失败商品，等待定时任务重试",
        data={"success_count": success_count, "total_count": len(req.ids)},
    )


@router.get("/items/{item_pk}", response_model=ApiResponse)
async def get_listing_monitor_item(
    item_pk: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """查询单条采集商品的完整信息（含数据库中采集到的详情/原始数据）"""
    owner_id, _ = resolve_owner_scope(current_user)
    svc = ListingMonitorService(session)
    data = await svc.get_item(owner_id, item_pk)
    if not data:
        return ApiResponse(success=False, message="采集商品不存在")
    return ApiResponse(success=True, message="查询成功", data={"item": data})
