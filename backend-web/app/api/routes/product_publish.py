"""
商品发布 API 路由

功能：
1. 素材库管理（CRUD）
2. 单品发布（触发 Playwright 自动化）
3. 批量发布（后台任务异步执行）
4. 发布日志查询（分页+过滤）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db_session
from app.services.product_publish_service import ProductMaterialService
from app.services.publish_batch_status_service import PublishBatchStatusService
from app.services.publish_execution_service import PublishExecutorService, PublishLogService
from common.models.user import User, UserRole
from common.schemas.common import ApiResponse
from common.utils.local_image_upload import ImageUploadError, save_uploaded_image
from common.utils.time_utils import get_beijing_now_naive

def _is_admin(user: User) -> bool:
    """判断用户是否为管理员"""
    return user.role == UserRole.ADMIN

router = APIRouter(prefix="/product-publish", tags=["商品发布"])


# ==================== Pydantic 请求 / 响应模型 ====================

class MaterialCreateRequest(BaseModel):
    """创建素材请求"""
    title: str = Field(..., min_length=1, max_length=200, description="商品标题")
    description: str = Field(..., min_length=1, description="商品描述")
    price: float = Field(..., gt=0, description="售价")
    original_price: Optional[float] = Field(None, description="原价（划线价）")
    category: Optional[str] = Field(None, max_length=100, description="商品分类")
    images: List[str] = Field(default=[], description="图片URL列表（最多9张）")
    delivery_method: str = Field("express", description="发货方式：express/pickup")
    postage: float = Field(0, ge=0, description="邮费，0表示包邮")
    address: Optional[str] = Field(None, max_length=200, description="宝贝所在地")
    brand: Optional[str] = Field(None, max_length=100, description="品牌")
    condition: str = Field("全新", description="成色")
    remark: Optional[str] = Field(None, max_length=500, description="备注（内部使用）")


class MaterialUpdateRequest(BaseModel):
    """更新素材请求（所有字段均可选）"""
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    original_price: Optional[float] = None
    category: Optional[str] = None
    images: Optional[List[str]] = None
    delivery_method: Optional[str] = None
    postage: Optional[float] = Field(None, ge=0)
    address: Optional[str] = None
    brand: Optional[str] = None
    condition: Optional[str] = None
    remark: Optional[str] = None


class PublishSingleRequest(BaseModel):
    """单品发布请求"""
    account_id: str = Field(..., description="闲鱼账号ID（cookie_id）")
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(...)
    price: float = Field(..., gt=0)
    original_price: Optional[float] = None
    category: Optional[str] = Field(None, description="商品分类")
    images: List[str] = Field(..., min_length=1, description="图片本地路径列表（至少1张）")
    address: Optional[str] = None
    delivery_method: str = Field("express", description="发货方式：express/pickup")
    postage: float = Field(0, ge=0, description="邮费，0表示包邮")
    brand: Optional[str] = Field(None, description="品牌")
    condition: str = Field("全新", description="成色")


class BatchPublishRequest(BaseModel):
    """批量发布请求"""
    account_ids: List[str] = Field(..., min_length=1, description="账号ID列表")
    material_ids: List[int] = Field(..., min_length=1, description="素材ID列表")


# ==================== 素材库接口 ====================

@router.post("/materials", response_model=ApiResponse)
async def create_material(
    req: MaterialCreateRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """创建商品素材"""
    svc = ProductMaterialService(session)
    material = await svc.create(current_user.id, req.model_dump())
    return ApiResponse(success=True, message="素材创建成功", data={"id": material.id})


@router.get("/materials", response_model=ApiResponse)
async def list_materials(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, description="每页条数"),
    title: str = Query(None, description="标题模糊搜索"),
    category: str = Query(None, description="分类筛选"),
    condition: str = Query(None, description="成色筛选"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """分页查询素材列表（管理员可查看所有用户的素材）"""
    svc = ProductMaterialService(session)
    # 管理员查看全部，普通用户只看自己的
    query_user_id = None if _is_admin(current_user) else current_user.id
    data = await svc.list_materials(
        query_user_id, page=page, page_size=page_size,
        title=title, category=category, condition=condition,
    )
    # 管理员场景：批量补充用户名
    if _is_admin(current_user) and data.get("list"):
        from sqlalchemy import select
        user_ids = list({m["user_id"] for m in data["list"]})
        stmt = select(User.id, User.username).where(User.id.in_(user_ids))
        rows = (await session.execute(stmt)).all()
        name_map = {r.id: r.username for r in rows}
        for m in data["list"]:
            m["username"] = name_map.get(m["user_id"], "未知用户")
    return ApiResponse(success=True, message="查询成功", data=data)


class BatchDeleteRequest(BaseModel):
    """批量删除素材请求"""
    ids: List[int] = Field(..., min_length=1, description="素材ID列表")


@router.post("/materials/batch-delete", response_model=ApiResponse)
async def batch_delete_materials(
    req: BatchDeleteRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """批量删除素材（管理员可删除任意素材）"""
    svc = ProductMaterialService(session)
    query_user_id = None if _is_admin(current_user) else current_user.id
    count = await svc.batch_delete(req.ids, query_user_id)
    return ApiResponse(success=True, message=f"成功删除 {count} 条素材", data={"deleted_count": count})


@router.get("/materials/{material_id}", response_model=ApiResponse)
async def get_material(
    material_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """获取单条素材详情（管理员可访问任意素材）"""
    svc = ProductMaterialService(session)
    query_user_id = None if _is_admin(current_user) else current_user.id
    material = await svc.get(material_id, query_user_id)
    if not material:
        return ApiResponse(success=False, message="素材不存在或无权访问")
    from app.services.product_publish_service import _material_to_dict
    return ApiResponse(success=True, message="查询成功", data=_material_to_dict(material))


@router.put("/materials/{material_id}", response_model=ApiResponse)
async def update_material(
    material_id: int,
    req: MaterialUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """更新素材信息（管理员可修改任意素材）"""
    svc = ProductMaterialService(session)
    query_user_id = None if _is_admin(current_user) else current_user.id
    updated = await svc.update(
        material_id,
        query_user_id,
        {k: v for k, v in req.model_dump().items() if v is not None},
    )
    if not updated:
        return ApiResponse(success=False, message="素材不存在或无权修改")
    return ApiResponse(success=True, message="素材更新成功")


@router.delete("/materials/{material_id}", response_model=ApiResponse)
async def delete_material(
    material_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """删除素材（管理员可删除任意素材）"""
    svc = ProductMaterialService(session)
    query_user_id = None if _is_admin(current_user) else current_user.id
    deleted = await svc.delete(material_id, query_user_id)
    if not deleted:
        return ApiResponse(success=False, message="素材不存在或无权删除")
    return ApiResponse(success=True, message="素材删除成功")


# ==================== 发布接口 ====================

@router.post("/publish/single", response_model=ApiResponse)
async def publish_single(
    req: PublishSingleRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """单品发布（同步执行，等待 Playwright 完成后返回结果）
    
    注意：发布操作会启动无头浏览器，耗时约 30-60 秒，请前端设置合适的超时时间。
    """
    svc = PublishExecutorService(session)
    result = await svc.publish_single(
        user_id=current_user.id,
        account_id=req.account_id,
        item_data=req.model_dump(),
    )
    return ApiResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        data={
            "item_url": result.get("item_url"),
            "item_id": result.get("item_id"),
            "log_id": result.get("log_id"),
            "sync_status": result.get("sync_status"),
            "sync_message": result.get("sync_message"),
            "sync_total_count": result.get("sync_total_count"),
            "sync_saved_count": result.get("sync_saved_count"),
        },
    )


@router.post("/publish/batch", response_model=ApiResponse)
async def publish_batch(
    req: BatchPublishRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """批量发布（后台异步执行，立即返回 batch_id）
    
    前端通过 GET /publish/batch/{batch_id}/status 查询进度。
    后台会按账号循环，每个账号依次发布所有素材，复用同一浏览器实例。
    """
    mat_svc = ProductMaterialService(session)
    from app.services.product_publish_service import _material_to_dict
    materials = [_material_to_dict(m) for m in await mat_svc.list_by_ids(req.material_ids, current_user.id)]

    if not materials:
        return ApiResponse(success=False, message="没有找到有效的素材")

    batch_id = str(uuid.uuid4())
    await PublishBatchStatusService.init_batch(
        batch_id=batch_id,
        account_ids=req.account_ids,
        material_count=len(materials),
    )

    # 创建后台任务
    background_tasks.add_task(
        _run_batch_publish_background,
        user_id=current_user.id,
        account_ids=req.account_ids,
        materials=materials,
        batch_id=batch_id,
    )

    return ApiResponse(
        success=True,
        message=f"批量发布任务已提交，共 {len(req.account_ids)} 个账号 × {len(materials)} 件商品",
        data={
            "batch_id": batch_id,
            "total": len(req.account_ids) * len(materials),
        },
    )


@router.get("/publish/batch/{batch_id}/status", response_model=ApiResponse)
async def get_batch_status(
    batch_id: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """查询批量发布任务进度"""
    from sqlalchemy import select, func
    from common.models.publish_log import PublishLog

    unknown_sync_message = "批量任务同步状态缓存不存在，无法判断自动获取商品结果"

    stmt = select(
        PublishLog.status,
        func.count().label("cnt"),
    ).where(
        PublishLog.batch_id == batch_id,
        PublishLog.user_id == current_user.id,
    ).group_by(PublishLog.status)

    rows = (await session.execute(stmt)).all()
    counts = {r.status: r.cnt for r in rows}

    account_stmt = select(
        PublishLog.account_id,
        PublishLog.status,
        func.count().label("cnt"),
    ).where(
        PublishLog.batch_id == batch_id,
        PublishLog.user_id == current_user.id,
    ).group_by(PublishLog.account_id, PublishLog.status)
    account_rows = (await session.execute(account_stmt)).all()

    account_count_map: Dict[str, Dict[str, int]] = {}
    for row in account_rows:
        status_map = account_count_map.setdefault(row.account_id, {})
        status_map[row.status] = int(row.cnt)

    total = sum(counts.values())
    success = counts.get("success", 0)
    failed = counts.get("failed", 0)
    publishing = counts.get("publishing", 0)
    pending = counts.get("pending", 0)
    batch_snapshot = await PublishBatchStatusService.get_batch_snapshot(batch_id)

    if batch_snapshot is None:
        if total == 0:
            return ApiResponse(success=False, message="批量任务不存在或状态已失效")
        return ApiResponse(success=False, message="批量任务状态已失效，请到发布日志查看执行结果")

    account_statuses: List[Dict[str, Any]] = []
    if batch_snapshot:
        material_count = int(batch_snapshot.get("material_count") or 0)
        account_order = batch_snapshot.get("account_order") or []
        account_sync_map = batch_snapshot.get("accounts") or {}
        expected_total = material_count * len(account_order)
        if expected_total > total:
            total = expected_total
            pending = max(total - success - failed - publishing, 0)

        for account_id in account_order:
            status_map = account_count_map.get(account_id, {})
            account_total = material_count if material_count > 0 else sum(status_map.values())
            account_success = int(status_map.get("success", 0))
            account_failed = int(status_map.get("failed", 0))
            account_publishing = int(status_map.get("publishing", 0))
            account_pending = max(account_total - account_success - account_failed - account_publishing, 0)
            sync_info = account_sync_map.get(account_id, {})
            account_statuses.append(
                {
                    "account_id": account_id,
                    "total": account_total,
                    "success": account_success,
                    "failed": account_failed,
                    "publishing": account_publishing,
                    "pending": account_pending,
                    "sync_status": sync_info.get("sync_status", "pending"),
                    "sync_message": sync_info.get("sync_message", "等待该账号发布完成后自动获取商品"),
                    "sync_total_count": int(sync_info.get("sync_total_count") or 0),
                    "sync_saved_count": int(sync_info.get("sync_saved_count") or 0),
                }
            )

        extra_account_ids = [account_id for account_id in account_count_map.keys() if account_id not in set(account_order)]
        for account_id in extra_account_ids:
            status_map = account_count_map.get(account_id, {})
            account_total = sum(status_map.values())
            account_success = int(status_map.get("success", 0))
            account_failed = int(status_map.get("failed", 0))
            account_publishing = int(status_map.get("publishing", 0))
            account_pending = int(status_map.get("pending", 0))
            account_statuses.append(
                {
                    "account_id": account_id,
                    "total": account_total,
                    "success": account_success,
                    "failed": account_failed,
                    "publishing": account_publishing,
                    "pending": account_pending,
                    "sync_status": "unknown",
                    "sync_message": unknown_sync_message,
                    "sync_total_count": 0,
                    "sync_saved_count": 0,
                }
            )
    sync_finished = all(
        account_status.get("sync_status") in {"success", "failed", "skipped", "unknown"}
        for account_status in account_statuses
    ) if account_statuses else True

    return ApiResponse(
        success=True,
        message="查询成功",
        data={
            "batch_id": batch_id,
            "total": total,
            "success": success,
            "failed": failed,
            "publishing": publishing,
            "pending": pending,
            "finished": total > 0 and (publishing + pending) == 0 and sync_finished,
            "account_statuses": account_statuses,
        },
    )


# ==================== 发布日志接口 ====================

@router.get("/logs", response_model=ApiResponse)
async def list_publish_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20),
    account_id: Optional[str] = Query(None, description="按账号过滤"),
    status: Optional[str] = Query(None, description="按状态过滤：pending/publishing/success/failed"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """分页查询发布日志（管理员可查看所有用户的发布日志）"""
    svc = PublishLogService(session)
    # 管理员查看全部，普通用户只看自己的
    query_user_id = None if _is_admin(current_user) else current_user.id
    data = await svc.list_logs(
        user_id=query_user_id,
        page=page,
        page_size=page_size,
        account_id=account_id,
        status=status,
    )
    # 管理员场景：批量补充用户名
    if _is_admin(current_user) and data.get("list"):
        from sqlalchemy import select
        user_ids = list({log["user_id"] for log in data["list"]})
        stmt = select(User.id, User.username).where(User.id.in_(user_ids))
        rows = (await session.execute(stmt)).all()
        name_map = {r.id: r.username for r in rows}
        for log in data["list"]:
            log["username"] = name_map.get(log["user_id"], "未知用户")
    return ApiResponse(success=True, message="查询成功", data=data)


@router.delete("/logs/clear", response_model=ApiResponse)
async def clear_publish_logs(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """清空发布日志（只清空10天前的数据）"""
    from datetime import timedelta

    from loguru import logger
    from sqlalchemy import delete

    from common.models.publish_log import PublishLog

    try:
        ten_days_ago = get_beijing_now_naive() - timedelta(days=10)
        stmt = delete(PublishLog).where(
            PublishLog.user_id == current_user.id,
            PublishLog.created_at < ten_days_ago,
        )

        result = await session.execute(stmt)
        await session.commit()

        deleted_count = result.rowcount or 0
        logger.info(f"[发布日志] 用户 {current_user.id} 已清空 {deleted_count} 条10天前的日志")
        return ApiResponse(
            success=True,
            message=f"已清空 {deleted_count} 条10天前的发布日志",
        )
    except Exception as e:
        await session.rollback()
        logger.error(f"[发布日志] 清空日志失败: {e}")
        return ApiResponse(success=False, message=f"清空发布日志失败: {str(e)}")


# ==================== 图片上传接口 ====================

@router.post("/upload/images", response_model=ApiResponse)
async def upload_product_images(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """上传商品图片（支持多张，最多9张，每张最大5MB）

    返回本地文件路径列表，这些路径将直接传给 Playwright 的 set_input_files。
    """
    from app.core.paths import get_upload_path

    upload_dir = get_upload_path("products")

    if len(files) > 9:
        return ApiResponse(success=False, message="最多上传9张图片")

    saved_paths: List[str] = []
    saved_urls: List[str] = []

    for file in files:
        try:
            filepath, filename, _ = await save_uploaded_image(
                file,
                upload_dir,
            )
        except ImageUploadError as exc:
            # 在消息里带上具体哪张图片出错，方便前端展示
            return ApiResponse(
                success=False,
                message=f"文件 {file.filename}: {exc.message}",
            )

        saved_paths.append(str(filepath))                          # 绝对路径，用于 Playwright
        saved_urls.append(f"/static/uploads/products/{filename}")  # URL，用于前端预览

    return ApiResponse(
        success=True,
        message=f"成功上传 {len(saved_paths)} 张图片",
        data={"paths": saved_paths, "urls": saved_urls},
    )


# ==================== 后台任务函数 ====================

async def _run_batch_publish_background(
    user_id: int,
    account_ids: List[str],
    materials: List[dict],
    batch_id: str,
) -> None:
    """后台异步执行批量发布任务"""
    from common.db.session import async_session_maker
    from loguru import logger
    import traceback

    async with async_session_maker() as session:
        svc = PublishExecutorService(session)
        try:
            # 直接将 batch_id 传给 service，确保日志与路由返回值一致
            await svc.batch_publish(
                user_id=user_id,
                account_ids=account_ids,
                materials=materials,
                batch_id=batch_id,
            )
        except Exception as e:
            logger.error(f"批量发布后台任务异常: {e}\n{traceback.format_exc()}")
            await PublishBatchStatusService.clear_batch(batch_id)