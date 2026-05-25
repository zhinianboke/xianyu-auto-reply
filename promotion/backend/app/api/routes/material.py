"""
返佣系统 - 素材库API路由

功能：
1. 素材列表查询（分页 + 关键词搜索）
2. 更新素材信息
3. 删除素材
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models import User, UserRole

router = APIRouter()


class MaterialUpdateBody(BaseModel):
    """更新素材请求体"""
    title: str | None = Field(default=None, description="商品标题")
    price: float | None = Field(default=None, description="售价")
    description: str | None = Field(default=None, description="商品描述")
    images: str | None = Field(default=None, description="商品图片JSON")
    click_url: str | None = Field(default=None, description="推广链接")
    coupon_url: str | None = Field(default=None, description="券二合一推广链接")
    coupon_info: str | None = Field(default=None, description="优惠券信息")
    tpwd: str | None = Field(default=None, description="淘口令")
    short_url: str | None = Field(default=None, description="短连接")


@router.get("/list")
async def list_materials(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    keyword: str = Query(default="", description="搜索关键词"),
    account_id: str = Query(default="", description="闲鱼账号筛选"),
    publish_status: str = Query(default="", description="发布状态筛选（unpublished/published/failed，空=全部）"),
    published: str = Query(default="", description="兼容旧版发布状态筛选（1=已发布，0=未发布）"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """分页查询素材库（管理员可看所有用户数据，支持发布状态筛选）"""
    from app.services.material_service import list_materials as do_list
    return await do_list(
        session=session, user_id=current_user.id,
        page=page, page_size=page_size, keyword=keyword, account_id=account_id,
        is_admin=(current_user.role == UserRole.ADMIN),
        publish_status=publish_status,
        legacy_published=published,
    )


@router.put("/update/{material_id}")
async def update_material(
    material_id: int,
    body: MaterialUpdateBody,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """更新素材信息"""
    from app.services.material_service import update_material as do_update
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return await do_update(session=session, user_id=current_user.id, material_id=material_id, data=data)


@router.delete("/delete/{material_id}")
async def delete_material(
    material_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """删除素材"""
    from app.services.material_service import delete_material as do_delete
    return await do_delete(session=session, user_id=current_user.id, material_id=material_id)


class BatchDeleteBody(BaseModel):
    """批量删除请求体"""
    ids: list[int] = Field(description="素材ID列表")


@router.post("/batch-delete")
async def batch_delete_materials(
    body: BatchDeleteBody,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """批量删除素材"""
    from app.services.material_service import batch_delete_materials as do_batch_delete
    return await do_batch_delete(session=session, user_id=current_user.id, ids=body.ids)
