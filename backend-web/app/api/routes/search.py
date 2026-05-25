"""
商品搜索路由

提供闲鱼商品搜索接口
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.services.search import search_xianyu_items
from app.api.deps import get_db_session as get_db
from common.models import User
from common.schemas.common import ApiResponse

router = APIRouter(prefix="/search", tags=["商品搜索"])


class ItemSearchRequest(BaseModel):
    """商品搜索请求"""
    keyword: str = Field(..., min_length=1, max_length=100, description="搜索关键词")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


@router.post("/items")
async def search_items(
    request: ItemSearchRequest,
    current_user: User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """
    搜索闲鱼商品
    
    使用Playwright进行商品搜索，支持自动处理滑块验证
    """
    try:
        logger.info(
            f"用户 {current_user.id} 搜索商品: keyword={request.keyword}, "
            f"page={request.page}, page_size={request.page_size}"
        )
        
        # 调用搜索服务
        result = await search_xianyu_items(
            keyword=request.keyword,
            page=request.page,
            page_size=request.page_size,
            db_session=db
        )
        
        # 检查是否有错误
        if result.get("error"):
            logger.error(f"商品搜索失败: {result['error']}")
            return ApiResponse(
                success=False,
                message=result["error"],
            )
        
        items = result.get("items", [])
        total = result.get("total", 0)
        
        logger.info(f"商品搜索成功: 找到 {total} 个商品")
        
        return ApiResponse(
            success=True,
            message="搜索成功",
            data={
                "items": items,
                "total": total,
                "page": request.page,
                "page_size": request.page_size,
            }
        )
        
    except Exception as e:
        logger.exception(f"商品搜索异常: {str(e)}")
        return ApiResponse(
            success=False,
            message=f"搜索失败: {str(e)}",
        )
