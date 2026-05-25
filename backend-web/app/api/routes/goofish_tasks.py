"""
Goofish 采集任务管理路由模块

提供 Goofish 采集任务的 CRUD 和启动/停止接口
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from app.api.deps import get_db_session as get_db
from common.models.goofish_crawl_job import GoofishCrawlJob as GoofishCrawlTask
from common.models.goofish_crawl_item import GoofishCrawlItem
from common.schemas.common import ApiResponse
from app.services.goofish_crawler import get_goofish_crawl_manager

from common.utils.time_utils import safe_isoformat
router = APIRouter(prefix="/goofish/tasks", tags=["Goofish采集任务"])

# 获取全局管理器实例
goofish_crawl_manager = get_goofish_crawl_manager()


class GoofishTaskCreate(BaseModel):
    """创建 Goofish 采集任务"""
    name: str = Field(..., description="任务名称")
    keyword: str = Field(..., description="搜索关键词")
    account_id: int = Field(..., description="使用的账号ID")
    start_page: int = Field(1, ge=1, description="起始页码")
    pages: int = Field(1, ge=1, description="抓取页数")
    page_size: int = Field(20, ge=1, description="每页数量")
    fetch_detail: bool = Field(True, description="是否抓取详情")
    detail_limit: int = Field(20, ge=0, description="详情抓取数量限制")
    interval_seconds: int = Field(3600, ge=60, description="执行间隔（秒）")
    enabled: bool = Field(True, description="是否启用")


class GoofishTaskUpdate(BaseModel):
    """更新 Goofish 采集任务"""
    name: Optional[str] = Field(None, description="任务名称")
    keyword: Optional[str] = Field(None, description="搜索关键词")
    account_id: Optional[int] = Field(None, description="使用的账号ID")
    start_page: Optional[int] = Field(None, ge=1, description="起始页码")
    pages: Optional[int] = Field(None, ge=1, description="抓取页数")
    page_size: Optional[int] = Field(None, ge=1, description="每页数量")
    fetch_detail: Optional[bool] = Field(None, description="是否抓取详情")
    detail_limit: Optional[int] = Field(None, ge=0, description="详情抓取数量限制")
    interval_seconds: Optional[int] = Field(None, ge=60, description="执行间隔（秒）")
    enabled: Optional[bool] = Field(None, description="是否启用")


@router.get("")
async def get_tasks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db)
) -> ApiResponse:
    """
    查询采集任务列表
    """
    try:
        # 查询总数
        count_result = await db.execute(select(GoofishCrawlTask))
        total = len(count_result.scalars().all())
        
        # 查询分页数据
        offset = (page - 1) * page_size
        query = (
            select(GoofishCrawlTask)
            .order_by(desc(GoofishCrawlTask.created_at))
            .offset(offset)
            .limit(page_size)
        )
        
        result = await db.execute(query)
        tasks = result.scalars().all()
        
        # 获取运行状态
        running_task_ids = goofish_crawl_manager.get_running_tasks()
        
        task_list = []
        for task in tasks:
            task_list.append({
                "id": task.id,
                "name": task.name,
                "keyword": task.keyword,
                "account_id": task.account_id,
                "start_page": task.start_page,
                "pages": task.pages,
                "page_size": task.page_size,
                "fetch_detail": task.fetch_detail,
                "detail_limit": task.detail_limit,
                "interval_seconds": task.interval_seconds,
                "enabled": task.enabled,
                "running": task.id in running_task_ids,
                "last_run_time": safe_isoformat(task.last_run_time),
                "created_at": safe_isoformat(task.created_at)
            })
        
        return ApiResponse(
            success=True,
            message="查询成功",
            data={
                "list": task_list,
                "total": total,
                "page": page,
                "page_size": page_size
            }
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"查询失败: {str(e)}",
            data=None
        )


@router.post("")
async def create_task(
    task_data: GoofishTaskCreate,
    db: AsyncSession = Depends(get_db)
) -> ApiResponse:
    """
    创建采集任务
    """
    try:
        new_task = GoofishCrawlTask(
            name=task_data.name,
            keyword=task_data.keyword,
            account_id=task_data.account_id,
            start_page=task_data.start_page,
            pages=task_data.pages,
            page_size=task_data.page_size,
            fetch_detail=task_data.fetch_detail,
            detail_limit=task_data.detail_limit,
            interval_seconds=task_data.interval_seconds,
            enabled=task_data.enabled
        )
        
        db.add(new_task)
        await db.commit()
        await db.refresh(new_task)
        
        return ApiResponse(
            success=True,
            message="创建成功",
            data={"id": new_task.id}
        )
        
    except Exception as e:
        await db.rollback()
        return ApiResponse(
            success=False,
            message=f"创建失败: {str(e)}",
            data=None
        )


@router.put("/{task_id}")
async def update_task(
    task_id: int,
    task_data: GoofishTaskUpdate,
    db: AsyncSession = Depends(get_db)
) -> ApiResponse:
    """
    更新采集任务
    """
    try:
        result = await db.execute(
            select(GoofishCrawlTask).where(GoofishCrawlTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        
        if not task:
            return ApiResponse(
                success=False,
                message="任务不存在",
                data=None
            )
        
        # 更新字段
        if task_data.name is not None:
            task.name = task_data.name
        if task_data.keyword is not None:
            task.keyword = task_data.keyword
        if task_data.account_id is not None:
            task.account_id = task_data.account_id
        if task_data.start_page is not None:
            task.start_page = task_data.start_page
        if task_data.pages is not None:
            task.pages = task_data.pages
        if task_data.page_size is not None:
            task.page_size = task_data.page_size
        if task_data.fetch_detail is not None:
            task.fetch_detail = task_data.fetch_detail
        if task_data.detail_limit is not None:
            task.detail_limit = task_data.detail_limit
        if task_data.interval_seconds is not None:
            task.interval_seconds = task_data.interval_seconds
        if task_data.enabled is not None:
            task.enabled = task_data.enabled
        
        await db.commit()
        
        return ApiResponse(
            success=True,
            message="更新成功",
            data=None
        )
        
    except Exception as e:
        await db.rollback()
        return ApiResponse(
            success=False,
            message=f"更新失败: {str(e)}",
            data=None
        )


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db)
) -> ApiResponse:
    """
    删除采集任务
    """
    try:
        # 检查任务是否正在运行
        if goofish_crawl_manager.is_running(task_id):
            return ApiResponse(
                success=False,
                message="任务正在运行，请先停止任务",
                data=None
            )
        
        result = await db.execute(
            select(GoofishCrawlTask).where(GoofishCrawlTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        
        if not task:
            return ApiResponse(
                success=False,
                message="任务不存在",
                data=None
            )
        
        await db.delete(task)
        await db.commit()
        
        return ApiResponse(
            success=True,
            message="删除成功",
            data=None
        )
        
    except Exception as e:
        await db.rollback()
        return ApiResponse(
            success=False,
            message=f"删除失败: {str(e)}",
            data=None
        )


@router.post("/{task_id}/start")
async def start_task(
    task_id: int,
    db: AsyncSession = Depends(get_db)
) -> ApiResponse:
    """
    启动采集任务
    """
    try:
        goofish_crawl_manager.start_job(job_id=task_id)
        return ApiResponse(
            success=True,
            message="任务已启动",
            data=None
        )
    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"启动失败: {str(e)}",
            data=None
        )


@router.post("/{task_id}/stop")
async def stop_task(
    task_id: int
) -> ApiResponse:
    """
    停止采集任务
    """
    try:
        await goofish_crawl_manager.stop_job(job_id=task_id)
        return ApiResponse(
            success=True,
            message="任务已停止",
            data=None
        )
    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"停止失败: {str(e)}",
            data=None
        )


@router.get("/{task_id}/items")
async def get_task_items(
    task_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db)
) -> ApiResponse:
    """
    查询任务采集的商品列表
    """
    try:
        # 查询总数
        count_result = await db.execute(
            select(GoofishCrawlItem).where(GoofishCrawlItem.task_id == task_id)
        )
        total = len(count_result.scalars().all())
        
        # 查询分页数据
        offset = (page - 1) * page_size
        query = (
            select(GoofishCrawlItem)
            .where(GoofishCrawlItem.task_id == task_id)
            .order_by(desc(GoofishCrawlItem.created_at))
            .offset(offset)
            .limit(page_size)
        )
        
        result = await db.execute(query)
        items = result.scalars().all()
        
        item_list = []
        for item in items:
            item_list.append({
                "id": item.id,
                "item_id": item.item_id,
                "title": item.title,
                "price": item.price,
                "view_count": item.view_count,
                "want_count": item.want_count,
                "description": item.description,
                "seller_nick": item.seller_nick,
                "item_url": item.item_url,
                "image_url": item.image_url,
                "created_at": safe_isoformat(item.created_at),
                "updated_at": safe_isoformat(item.updated_at)
            })
        
        return ApiResponse(
            success=True,
            message="查询成功",
            data={
                "list": item_list,
                "total": total,
                "page": page,
                "page_size": page_size
            }
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"查询失败: {str(e)}",
            data=None
        )
