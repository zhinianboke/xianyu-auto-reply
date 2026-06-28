"""
弹窗公告路由

功能：
1. 获取启用中的弹窗公告（所有用户，用于登录后弹窗展示）
2. 获取弹窗公告列表（仅管理员，分页，过滤已删除）
3. 新增弹窗公告（仅管理员）
4. 修改弹窗公告（仅管理员）
5. 启用/停用弹窗公告（仅管理员）
6. 删除弹窗公告（仅管理员，软删除）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Header
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user, get_db_session
from common.models.user import User
from common.models.popup_announcement import PopupAnnouncement
from common.schemas.common import ApiResponse
from common.utils.text_utils import escape_xss
from common.utils.time_utils import safe_isoformat
from common.utils.pagination import execute_paginated_with_filters
from app.services.remote_content_service import (
    fetch_remote_public_popup_announcements,
    is_remote_fetch_request,
)

router = APIRouter(tags=["popup_announcements"])

# 登录弹窗展示的最大条数
_PUBLIC_POPUP_LIMIT = 10


class PopupAnnouncementCreate(BaseModel):
    """创建弹窗公告请求"""
    title: str
    content: str
    link: str | None = None
    is_enabled: bool = True


class PopupAnnouncementUpdate(BaseModel):
    """更新弹窗公告请求"""
    title: str
    content: str
    link: str | None = None
    is_enabled: bool = True


def _serialize(item: PopupAnnouncement) -> dict:
    """序列化本地弹窗公告对象（来源标记为 local）"""
    return {
        "id": item.id,
        "title": item.title,
        "content": item.content,
        "link": item.link,
        "is_enabled": bool(item.is_enabled),
        "source": "local",
        "created_at": safe_isoformat(item.created_at),
        "updated_at": safe_isoformat(item.updated_at),
    }


@router.get("/public", response_model=ApiResponse)
async def get_public_popup_announcements(
    user_agent: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db_session),
):
    """
    获取启用中的弹窗公告（公开接口，用于用户登录后弹窗展示）

    返回内容 = 本地启用且未删除的弹窗公告 + 远程官方服务器的公开弹窗公告（与桌面版同源），
    远程弹窗公告以 source=remote 标记、ID 取负，避免与本地数据冲突。
    远程拉取失败时静默降级，仅返回本地弹窗公告。
    """
    # 查询本地启用中的弹窗公告（过滤已删除与停用）
    result = await db.execute(
        select(PopupAnnouncement)
        .where(
            PopupAnnouncement.is_deleted == False,
            PopupAnnouncement.is_enabled == True,
        )
        .order_by(desc(PopupAnnouncement.created_at))
        .limit(_PUBLIC_POPUP_LIMIT)
    )
    announcements = result.scalars().all()

    items = []
    # 本地去重键（标题, 内容），用于过滤远程重复弹窗公告
    dedup_keys: set[tuple[str | None, str | None]] = set()
    for item in announcements:
        items.append(_serialize(item))
        dedup_keys.add((item.title, item.content))

    # 合并远程官方弹窗公告（失败时返回空，不影响本地展示）；
    # 若请求本身来自服务器间远程拉取，则不再二次拉取，避免递归自调用
    if not is_remote_fetch_request(user_agent):
        remote_items = await fetch_remote_public_popup_announcements(local_dedup_keys=dedup_keys)
        items.extend(remote_items)

    return ApiResponse(success=True, data={"items": items})


@router.get("", response_model=ApiResponse)
async def get_popup_announcements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """获取弹窗公告列表（管理员，按创建时间倒序，过滤已删除）"""
    items, total = await execute_paginated_with_filters(
        db, PopupAnnouncement,
        filters=[PopupAnnouncement.is_deleted == False],
        order_by=[desc(PopupAnnouncement.created_at)],
        page=page, page_size=page_size,
    )

    return ApiResponse(
        success=True,
        data={
            "items": [_serialize(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("", response_model=ApiResponse)
async def create_popup_announcement(
    data: PopupAnnouncementCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """新增弹窗公告（仅管理员），对内容进行XSS转义"""
    if not data.title.strip():
        return ApiResponse(success=False, message="公告标题不能为空")
    if not data.content.strip():
        return ApiResponse(success=False, message="公告内容不能为空")

    item = PopupAnnouncement(
        title=escape_xss(data.title.strip()),
        content=escape_xss(data.content.strip()),
        link=(data.link.strip() or None) if data.link else None,
        is_enabled=data.is_enabled,
        is_deleted=False,
    )

    db.add(item)
    await db.commit()
    await db.refresh(item)

    return ApiResponse(success=True, message="弹窗公告发布成功", data={"id": item.id})


@router.put("/{popup_id}", response_model=ApiResponse)
async def update_popup_announcement(
    popup_id: int,
    data: PopupAnnouncementUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """修改弹窗公告（仅管理员），对内容进行XSS转义"""
    result = await db.execute(
        select(PopupAnnouncement).where(
            PopupAnnouncement.id == popup_id,
            PopupAnnouncement.is_deleted == False,
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        return ApiResponse(success=False, message="弹窗公告不存在")

    if not data.title.strip():
        return ApiResponse(success=False, message="公告标题不能为空")
    if not data.content.strip():
        return ApiResponse(success=False, message="公告内容不能为空")

    item.title = escape_xss(data.title.strip())
    item.content = escape_xss(data.content.strip())
    item.link = (data.link.strip() or None) if data.link else None
    item.is_enabled = data.is_enabled

    await db.commit()

    return ApiResponse(success=True, message="弹窗公告更新成功")


@router.put("/{popup_id}/toggle", response_model=ApiResponse)
async def toggle_popup_announcement(
    popup_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """启用/停用弹窗公告（仅管理员）"""
    result = await db.execute(
        select(PopupAnnouncement).where(
            PopupAnnouncement.id == popup_id,
            PopupAnnouncement.is_deleted == False,
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        return ApiResponse(success=False, message="弹窗公告不存在")

    item.is_enabled = not item.is_enabled
    await db.commit()

    return ApiResponse(
        success=True,
        message="已启用" if item.is_enabled else "已停用",
        data={"is_enabled": item.is_enabled},
    )


@router.delete("/{popup_id}", response_model=ApiResponse)
async def delete_popup_announcement(
    popup_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """删除弹窗公告（仅管理员，软删除）"""
    result = await db.execute(
        select(PopupAnnouncement).where(
            PopupAnnouncement.id == popup_id,
            PopupAnnouncement.is_deleted == False,
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        return ApiResponse(success=False, message="弹窗公告不存在")

    item.is_deleted = True
    await db.commit()

    return ApiResponse(success=True, message="弹窗公告删除成功")
