"""卡券关联弹窗的待选商品分页接口，只返回选择所需的轻量字段。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.services.selectable_item_service import SelectableItemService
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.auth_scope import resolve_owner_scope


router = APIRouter(prefix="/items/selectable", tags=["商品管理"])


@router.get("/paginated", response_model=ApiResponse)
async def get_selectable_items_paginated(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    keyword: str = Query(default="", max_length=255, description="商品名称或 ID"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """按用户权限读取待选页；参数为分页、关键词、认证用户和会话，返回统一响应。"""
    owner_id, _ = resolve_owner_scope(current_user)
    data = await SelectableItemService(session).get_page(owner_id, page, page_size, keyword)
    return ApiResponse(success=True, code=200, message="查询成功", data=data)
