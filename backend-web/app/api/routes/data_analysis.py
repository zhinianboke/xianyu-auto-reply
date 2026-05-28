"""
数据分析路由模块

提供卖家数据概览接口，支持多账号、多时间范围查询
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.api import deps
from app.services.data_analysis_service import fetch_browse_summary, fetch_seller_summary
from common.models import User
from common.models.xy_account import XYAccount
from common.schemas.common import ApiResponse
from common.utils.auth_scope import resolve_owner_scope

router = APIRouter(prefix="/data-analysis", tags=["数据分析"])


class SellerSummaryRequest(BaseModel):
    """卖家数据概览请求"""
    account_id: int = Field(..., description="账号ID")
    date_type: str = Field("recent7d", description="时间范围类型: recent1d/recent7d/recent30d")
    date_range: Optional[str] = Field("", description="自定义日期范围（可选）")


@router.post("/seller-summary")
async def get_seller_summary(
    request: SellerSummaryRequest,
    current_user: User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """
    获取卖家数据概览

    根据账号Cookie调用闲鱼卖家数据罗盘API，返回指定时间范围内的数据概览。
    支持近1天、近7天、近30天三种时间范围。

    Args:
        request: 请求参数（账号ID、时间范围）
        current_user: 当前登录用户
        db: 数据库会话

    Returns:
        ApiResponse: 包含卖家数据概览
    """
    # 查询账号信息（带权限检查）
    owner_id, is_admin = resolve_owner_scope(current_user)
    query = select(XYAccount).where(XYAccount.id == request.account_id)
    if not is_admin:
        query = query.where(XYAccount.owner_id == owner_id)

    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        return ApiResponse(success=False, message="账号不存在或无权限访问", data=None)

    if not account.cookie:
        return ApiResponse(success=False, message="账号Cookie为空，请先登录", data=None)

    # 校验date_type参数
    valid_date_types = ["recent1d", "recent7d", "recent30d", "customDate"]
    if request.date_type not in valid_date_types:
        return ApiResponse(
            success=False,
            message=f"无效的时间范围类型，支持: {', '.join(valid_date_types)}",
            data=None,
        )

    # 自定义日期范围校验
    if request.date_type == "customDate":
        if not request.date_range:
            return ApiResponse(
                success=False,
                message="自定义日期范围不能为空，格式: yyyyMMdd|yyyyMMdd",
                data=None,
            )
        parts = (request.date_range or "").split("|")
        if len(parts) != 2 or len(parts[0]) != 8 or len(parts[1]) != 8:
            return ApiResponse(
                success=False,
                message="日期范围格式错误，正确格式: yyyyMMdd|yyyyMMdd",
                data=None,
            )

    # 调用服务获取数据
    api_result = await fetch_seller_summary(
        cookies_str=account.cookie,
        date_type=request.date_type,
        date_range=request.date_range or "",
    )

    if api_result.get("success"):
        return ApiResponse(
            success=True,
            message="获取成功",
            data=api_result.get("data"),
        )
    else:
        return ApiResponse(
            success=False,
            message=api_result.get("message", "获取数据失败"),
            data=None,
        )


class BrowseSummaryRequest(BaseModel):
    """流量分布请求"""
    account_id: int = Field(..., description="账号ID")
    date_type: str = Field("recent7d", description="时间范围类型: recent1d/recent7d/recent30d/customDate")
    date_range: Optional[str] = Field("", description="自定义日期范围（可选，格式: yyyyMMdd|yyyyMMdd）")


@router.post("/browse-summary")
async def get_browse_summary(
    request: BrowseSummaryRequest,
    current_user: User = Depends(deps.get_current_active_user),
    db: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """
    获取流量分布数据

    返回来源分布、商品分布、时间分布、地域分布数据。

    Args:
        request: 请求参数（账号ID、时间范围）
        current_user: 当前登录用户
        db: 数据库会话

    Returns:
        ApiResponse: 包含流量分布数据
    """
    # 查询账号信息（带权限检查）
    owner_id, is_admin = resolve_owner_scope(current_user)
    query = select(XYAccount).where(XYAccount.id == request.account_id)
    if not is_admin:
        query = query.where(XYAccount.owner_id == owner_id)

    result = await db.execute(query)
    account = result.scalar_one_or_none()

    if not account:
        return ApiResponse(success=False, message="账号不存在或无权限访问", data=None)

    if not account.cookie:
        return ApiResponse(success=False, message="账号Cookie为空，请先登录", data=None)

    # 校验date_type参数
    valid_date_types = ["recent1d", "recent7d", "recent30d", "customDate"]
    if request.date_type not in valid_date_types:
        return ApiResponse(
            success=False,
            message=f"无效的时间范围类型，支持: {', '.join(valid_date_types)}",
            data=None,
        )

    # 自定义日期范围校验
    if request.date_type == "customDate":
        if not request.date_range:
            return ApiResponse(
                success=False,
                message="自定义日期范围不能为空，格式: yyyyMMdd|yyyyMMdd",
                data=None,
            )
        parts = (request.date_range or "").split("|")
        if len(parts) != 2 or len(parts[0]) != 8 or len(parts[1]) != 8:
            return ApiResponse(
                success=False,
                message="日期范围格式错误，正确格式: yyyyMMdd|yyyyMMdd",
                data=None,
            )

    # 调用服务获取数据
    api_result = await fetch_browse_summary(
        cookies_str=account.cookie,
        date_type=request.date_type,
        date_range=request.date_range or "",
    )

    if api_result.get("success"):
        return ApiResponse(
            success=True,
            message="获取成功",
            data=api_result.get("data"),
        )
    else:
        return ApiResponse(
            success=False,
            message=api_result.get("message", "获取数据失败"),
            data=None,
        )
