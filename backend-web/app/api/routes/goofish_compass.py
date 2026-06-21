"""
Goofish 数据罗盘路由模块

提供 Goofish 商品搜索和数据采集接口
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional

from app.api.deps import get_db_session as get_db, get_current_active_user
from common.models import User, UserRole
from common.models.xy_account import XYAccount as Cookie
from common.schemas.common import ApiResponse

router = APIRouter(prefix="/compass/goofish", tags=["Goofish数据罗盘"])


class GoofishSearchRequest(BaseModel):
    """Goofish 搜索请求"""
    keyword: str = Field(..., description="搜索关键词")
    account_id: int = Field(..., description="使用的账号ID")
    start_page: int = Field(1, ge=1, le=50, description="起始页码")
    pages: int = Field(1, ge=1, le=10, description="抓取页数")
    page_size: int = Field(20, ge=1, le=50, description="每页数量")
    fetch_detail: bool = Field(True, description="是否抓取商品详情")
    detail_limit: int = Field(20, ge=0, le=50, description="详情抓取数量限制")
    headless: bool = Field(True, description="是否使用无头模式")


@router.post("/search")
async def search_goofish(
    request: GoofishSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ApiResponse:
    """
    搜索 Goofish 商品
    
    Args:
        request: 搜索请求参数
        db: 数据库会话
        
    Returns:
        ApiResponse: 包含搜索结果
    """
    try:
        # 查询账号信息
        result = await db.execute(
            select(Cookie).where(Cookie.id == request.account_id)
        )
        cookie = result.scalar_one_or_none()
        
        if not cookie:
            return ApiResponse(
                success=False,
                message="账号不存在",
                data=None
            )

        # 账号归属校验：非管理员只能使用自己名下的账号，防止越权借用他人账号登录态发起搜索
        if current_user.role != UserRole.ADMIN and cookie.owner_id != current_user.id:
            return ApiResponse(
                success=False,
                message="无权使用该账号",
                data=None
            )

        if not cookie.cookie:
            return ApiResponse(
                success=False,
                message="账号 Cookie 为空，请先登录",
                data=None
            )
        
        # 导入 Goofish 数据罗盘服务
        try:
            from app.services.compass.goofish_compass import (
                GoofishCompassService,
                GoofishCompassConfig
            )
        except ImportError:
            return ApiResponse(
                success=False,
                message="Goofish 数据罗盘服务不可用",
                data=None
            )
        
        # 创建配置
        config = GoofishCompassConfig(
            headless=request.headless,
            detail_concurrency=3,
            navigation_timeout_ms=30000,
            network_idle_timeout_ms=15000,
            detail_response_timeout_ms=7000
        )
        
        # 创建服务实例
        service = GoofishCompassService(
            user_id=str(cookie.id),
            cookie_value=cookie.cookie,
            config=config
        )
        
        # 执行搜索
        search_result = await service.search(
            keyword=request.keyword,
            start_page=request.start_page,
            pages=request.pages,
            page_size=request.page_size,
            fetch_detail=request.fetch_detail,
            detail_limit=request.detail_limit
        )
        
        # 检查是否有错误
        if search_result.get("error"):
            return ApiResponse(
                success=False,
                message=search_result["error"],
                data=search_result
            )
        
        return ApiResponse(
            success=True,
            message="搜索成功",
            data=search_result
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"搜索失败: {str(e)}",
            data=None
        )
