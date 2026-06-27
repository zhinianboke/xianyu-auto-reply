"""
商品监控分类管理路由

功能：
1. 分类列表查询
2. 分类详情查询
3. 新建分类
4. 修改分类名称
5. 删除分类（软删除，需检查关联数据）
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db_session
from common.models.user import User
from common.schemas.common import ApiResponse
from common.services.listing_monitor_category_service import ListingMonitorCategoryService
from common.utils.auth_scope import resolve_owner_scope

router = APIRouter(prefix="/product-monitor/categories", tags=["商品监控分类"])


class CategoryCreateRequest(BaseModel):
    """创建分类请求"""
    name: str = Field(..., min_length=1, max_length=100, description="分类名称")


class CategoryUpdateRequest(BaseModel):
    """修改分类请求"""
    name: str = Field(..., min_length=1, max_length=100, description="分类名称")


@router.get("", summary="查询分类列表")
async def list_categories(
    include_deleted: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """查询分类列表（普通用户仅见自己的分类，管理员可见全部，按创建时间倒序）"""
    owner_id, _ = resolve_owner_scope(current_user)
    service = ListingMonitorCategoryService(db)
    categories = await service.list_categories(
        owner_id=owner_id, include_deleted=include_deleted
    )
    return ApiResponse(success=True, data=categories)


@router.get("/{category_id}", summary="查询分类详情")
async def get_category(
    category_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """查询单个分类详情（普通用户仅可查看自己的分类，管理员可查看全部）"""
    owner_id, _ = resolve_owner_scope(current_user)
    service = ListingMonitorCategoryService(db)
    category = await service.get_category(category_id, owner_id=owner_id)
    if not category:
        return ApiResponse(success=False, message="分类不存在或无权限访问")
    return ApiResponse(success=True, data=category)


@router.post("", summary="新建分类")
async def create_category(
    body: CategoryCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """新建分类（名称在同一用户下不能重复）"""
    try:
        service = ListingMonitorCategoryService(db)
        category = await service.create_category(
            owner_id=current_user.id, name=body.name
        )
        await db.commit()
        return ApiResponse(success=True, data=category, message="创建成功")
    except ValueError as e:
        await db.rollback()
        return ApiResponse(success=False, message=str(e))
    except Exception as e:
        await db.rollback()
        return ApiResponse(success=False, message=f"创建失败：{e}")


@router.put("/{category_id}", summary="修改分类")
async def update_category(
    category_id: int,
    body: CategoryUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """修改分类名称（名称在同一用户下不能重复）"""
    try:
        service = ListingMonitorCategoryService(db)
        category = await service.update_category(
            category_id=category_id, owner_id=current_user.id, name=body.name
        )
        await db.commit()
        return ApiResponse(success=True, data=category, message="修改成功")
    except ValueError as e:
        await db.rollback()
        return ApiResponse(success=False, message=str(e))
    except Exception as e:
        await db.rollback()
        return ApiResponse(success=False, message=f"修改失败：{e}")


@router.delete("/{category_id}", summary="删除分类")
async def delete_category(
    category_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse:
    """删除分类（软删除，有关联数据时禁止删除）"""
    try:
        service = ListingMonitorCategoryService(db)
        await service.delete_category(category_id=category_id, owner_id=current_user.id)
        await db.commit()
        return ApiResponse(success=True, message="删除成功")
    except ValueError as e:
        await db.rollback()
        return ApiResponse(success=False, message=str(e))
    except Exception as e:
        await db.rollback()
        return ApiResponse(success=False, message=f"删除失败：{e}")
