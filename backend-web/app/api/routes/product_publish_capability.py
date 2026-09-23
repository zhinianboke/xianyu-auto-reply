"""
商品发布账号能力接口。

功能：
1. 校验发布账号归属和 Cookie；
2. 返回鱼小铺状态、多规格能力和服务费配置。
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db_session
from app.services.account_service import AccountService
from common.models.user import User, UserRole
from common.schemas.common import ApiResponse
from common.services.xianyu_publish_service import (
    detect_publish_account_capability,
    ensure_publish_capability_reliable,
)


router = APIRouter(prefix="/product-publish/accounts", tags=["商品发布"])


@router.get("/{account_id}/capability", response_model=ApiResponse)
async def get_publish_account_capability(
    account_id: str,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """
    查询指定账号是否开通鱼小铺及其发布能力。

    Args:
        account_id: 闲鱼账号标识。
        current_user: 当前登录用户。
        session: 数据库会话。
    Returns:
        统一响应，成功时包含账号类型和服务费配置。
    """
    try:
        owner_id = None if current_user.role == UserRole.ADMIN else current_user.id
        account = await AccountService(session).get_account_for_user(owner_id, account_id)
        if not account:
            return ApiResponse(success=False, message="发布账号不存在或无权使用", data=None)
        if not (account.cookie or "").strip():
            return ApiResponse(success=False, message="发布账号缺少Cookie，请重新登录账号", data=None)

        result = await detect_publish_account_capability(
            cookie=account.cookie,
            account_id=account.account_id,
            owner_id=account.owner_id,
        )
        # 本接口只服务发布页：判定不可信时直接报错，让用户在选账号阶段就知道，
        # 而不是填完表单提交后才被发布链路拒绝
        result = ensure_publish_capability_reliable(result)
    except Exception as exc:
        logger.error(f"账号发布能力检测异常: account_id={account_id}, error={exc}")
        return ApiResponse(success=False, message=f"账号发布能力检测失败：{exc}", data=None)
    if not result.get("success"):
        return ApiResponse(
            success=False,
            message=result.get("message") or "账号发布能力检测失败",
            data=None,
        )
    return ApiResponse(
        success=True,
        message="账号发布能力检测成功",
        data={
            "account_id": account.account_id,
            "is_fish_shop": bool(result.get("is_fish_shop")),
            "support_sku_or_inventory": bool(result.get("support_sku_or_inventory")),
            "commission_config": result.get("commission_config") or {},
        },
    )


__all__ = ["router"]
