"""
公告管理路由

功能：
1. 获取公告列表（所有用户可查看，过滤已删除）
2. 新增公告（仅管理员）
3. 修改公告（仅管理员）
4. 删除公告（仅管理员，软删除）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Header
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_admin_user, get_db_session
from common.models.user import User
from common.models.announcement import Announcement
from common.schemas.common import ApiResponse
from common.utils.text_utils import escape_xss
from app.services.remote_content_service import (
    fetch_remote_public_announcements,
    is_remote_fetch_request,
)

from common.utils.time_utils import safe_isoformat
from common.utils.pagination import execute_paginated_with_filters
router = APIRouter(tags=["announcements"])

# 顶部公告展示的最大条数
_PUBLIC_ANNOUNCEMENT_LIMIT = 10


class AnnouncementCreate(BaseModel):
    """创建公告请求"""
    title: str
    content: str


class AnnouncementUpdate(BaseModel):
    """更新公告请求"""
    title: str
    content: str


def _serialize_announcement(ann: Announcement) -> dict:
    """序列化本地公告对象（来源标记为 local）"""
    return {
        "id": ann.id,
        "title": ann.title,
        "content": ann.content,
        "source": "local",
        "created_at": safe_isoformat(ann.created_at),
        "updated_at": safe_isoformat(ann.updated_at),
    }


@router.get("/public", response_model=ApiResponse)
async def get_public_announcements(
    user_agent: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db_session),
):
    """
    获取公告列表（公开接口，用于系统顶部公告展示）

    返回内容 = 本地最新公告 + 远程官方服务器的公开公告（与桌面版同源），
    远程公告以 source=remote 标记、ID 取负，避免与本地公告冲突。
    远程拉取失败时静默降级，仅返回本地公告。
    """
    # 查询本地最新公告（过滤已删除）
    result = await db.execute(
        select(Announcement)
        .where(Announcement.is_deleted == False)
        .order_by(desc(Announcement.created_at))
        .limit(_PUBLIC_ANNOUNCEMENT_LIMIT)
    )
    announcements = result.scalars().all()

    items = []
    # 本地去重键（标题, 内容），用于过滤远程重复公告
    dedup_keys: set[tuple[str | None, str | None]] = set()
    for ann in announcements:
        items.append(_serialize_announcement(ann))
        dedup_keys.add((ann.title, ann.content))

    # 合并远程官方公告（失败时返回空，不影响本地展示）；
    # 若请求本身来自服务器间远程拉取，则不再二次拉取，避免递归自调用
    if not is_remote_fetch_request(user_agent):
        remote_items = await fetch_remote_public_announcements(local_dedup_keys=dedup_keys)
        items.extend(remote_items)

    return ApiResponse(success=True, data={"items": items})


@router.get("", response_model=ApiResponse)
async def get_announcements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """获取公告列表（按创建时间倒序，过滤已删除）"""
    announcements, total = await execute_paginated_with_filters(
        db, Announcement,
        filters=[Announcement.is_deleted == False],
        order_by=[desc(Announcement.created_at)],
        page=page, page_size=page_size,
    )
    
    items = []
    for ann in announcements:
        items.append(_serialize_announcement(ann))
    
    return ApiResponse(
        success=True,
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("", response_model=ApiResponse)
async def create_announcement(
    data: AnnouncementCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """新增公告（仅管理员），对内容进行XSS转义"""
    if not data.title.strip():
        return ApiResponse(success=False, message="公告标题不能为空")
    if not data.content.strip():
        return ApiResponse(success=False, message="公告内容不能为空")
    
    # XSS转义
    safe_title = escape_xss(data.title.strip())
    safe_content = escape_xss(data.content.strip())
    
    announcement = Announcement(
        title=safe_title,
        content=safe_content,
        is_deleted=False,
    )
    
    db.add(announcement)
    await db.commit()
    await db.refresh(announcement)
    
    return ApiResponse(success=True, message="公告发布成功", data={"id": announcement.id})


@router.put("/{announcement_id}", response_model=ApiResponse)
async def update_announcement(
    announcement_id: int,
    data: AnnouncementUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """修改公告（仅管理员），对内容进行XSS转义"""
    result = await db.execute(
        select(Announcement).where(
            Announcement.id == announcement_id,
            Announcement.is_deleted == False
        )
    )
    announcement = result.scalar_one_or_none()
    
    if not announcement:
        return ApiResponse(success=False, message="公告不存在")
    
    if not data.title.strip():
        return ApiResponse(success=False, message="公告标题不能为空")
    if not data.content.strip():
        return ApiResponse(success=False, message="公告内容不能为空")
    
    # XSS转义
    announcement.title = escape_xss(data.title.strip())
    announcement.content = escape_xss(data.content.strip())
    
    await db.commit()
    
    return ApiResponse(success=True, message="公告更新成功")


@router.delete("/{announcement_id}", response_model=ApiResponse)
async def delete_announcement(
    announcement_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """删除公告（仅管理员，软删除）"""
    result = await db.execute(
        select(Announcement).where(
            Announcement.id == announcement_id,
            Announcement.is_deleted == False
        )
    )
    announcement = result.scalar_one_or_none()
    
    if not announcement:
        return ApiResponse(success=False, message="公告不存在")
    
    # 软删除
    announcement.is_deleted = True
    await db.commit()
    
    return ApiResponse(success=True, message="公告删除成功")
