"""
同意后发货配置路由

功能：
1. 管理账号的「同意后发货」配置（开关、通知用户信息、提货URL）
2. 推荐本系统内置提货页地址，供前端填写「提货URL」时提示
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.api import deps
from app.core.config import get_settings
from common.models.user import User
from common.models.xy_account import XYAccount
from common.utils.agree_deliver import (
    PICKUP_ORDER_ID_PARAM,
    PICKUP_ORDER_NO_PARAM,
    PICKUP_PUBLIC_URL_ENV,
    resolve_pickup_page_url,
)
from common.utils.auth_scope import resolve_owner_scope

router = APIRouter(tags=["同意后发货配置"])


# ==================== 请求/响应模型 ====================

class AgreeDeliverConfig(BaseModel):
    """同意后发货配置"""
    enabled: bool = False  # 是否开启同意后发货
    notify_message: Optional[str] = None  # 通知用户信息（文本域）
    pickup_url: Optional[str] = None  # 提货URL


class AgreeDeliverConfigResponse(BaseModel):
    """同意后发货配置响应"""
    success: bool
    message: str = ""
    data: Optional[AgreeDeliverConfig] = None


class PickupUrlSuggestion(BaseModel):
    """本系统提货页地址推荐"""
    pickup_url: str = ""  # 推荐填写的提货URL（本系统内置提货页）
    warning: str = ""  # 需要商家注意的提示（为空表示可直接使用）
    env_name: str = PICKUP_PUBLIC_URL_ENV  # 公网部署需配置的环境变量名
    example_url: str = ""  # 买家最终收到的完整链接示例（含订单参数）


class PickupUrlSuggestionResponse(BaseModel):
    """提货页地址推荐响应"""
    success: bool
    message: str = ""
    data: Optional[PickupUrlSuggestion] = None


# ==================== 路由 ====================

@router.get("/pickup-url/suggestion", response_model=PickupUrlSuggestionResponse)
async def get_pickup_url_suggestion(
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
):
    """推荐本系统内置提货页地址（供「提货URL」填写提示，公网地址以环境变量为准）"""
    try:
        # 商家当前访问后台的地址：优先 Origin，其次从 Referer 推导
        origin = (request.headers.get("origin") or "").strip()
        if not origin:
            referer = (request.headers.get("referer") or "").strip()
            if "://" in referer:
                scheme, rest = referer.split("://", 1)
                host = rest.split("/", 1)[0]
                if host:
                    origin = f"{scheme}://{host}"

        settings = get_settings()
        pickup_url, warning = resolve_pickup_page_url(
            getattr(settings, "frontend_public_url", ""), origin
        )
        example_url = ""
        if pickup_url:
            example_url = (
                f"{pickup_url}?{PICKUP_ORDER_NO_PARAM}=订单号"
                f"&{PICKUP_ORDER_ID_PARAM}=订单ID"
            )

        return PickupUrlSuggestionResponse(
            success=True,
            data=PickupUrlSuggestion(
                pickup_url=pickup_url,
                warning=warning,
                env_name=PICKUP_PUBLIC_URL_ENV,
                example_url=example_url,
            ),
        )
    except Exception as e:
        logger.error(f"获取提货页地址推荐失败: {e}")
        return PickupUrlSuggestionResponse(
            success=False,
            message=f"获取提货页地址推荐失败: {str(e)}"
        )


@router.get("/{account_id}", response_model=AgreeDeliverConfigResponse)
async def get_agree_deliver_config(
    account_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """获取账号的同意后发货配置（管理员可操作所有账号，普通用户仅限本人账号）"""
    try:
        # 管理员不限制 owner，普通用户仅能访问本人账号
        owner_id, is_admin = resolve_owner_scope(current_user)
        conditions = [XYAccount.account_id == account_id]
        if not is_admin:
            conditions.append(XYAccount.owner_id == owner_id)
        stmt = select(XYAccount).where(*conditions)
        result = await session.execute(stmt)
        account = result.scalars().first()

        if not account:
            return AgreeDeliverConfigResponse(
                success=False,
                message="账号不存在或无权限访问"
            )

        config = AgreeDeliverConfig(
            enabled=bool(account.agree_deliver_enabled),
            notify_message=account.agree_deliver_notify_message,
            pickup_url=account.agree_deliver_pickup_url,
        )

        return AgreeDeliverConfigResponse(success=True, data=config)

    except Exception as e:
        logger.error(f"获取同意后发货配置失败: {e}")
        return AgreeDeliverConfigResponse(
            success=False,
            message=f"获取同意后发货配置失败: {str(e)}"
        )


@router.put("/{account_id}", response_model=AgreeDeliverConfigResponse)
async def update_agree_deliver_config(
    account_id: str,
    config: AgreeDeliverConfig,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """更新账号的同意后发货配置（仅存储配置，发货逻辑后续接入）"""
    try:
        # 提货URL 校验：开启同意后发货时必填；填写时校验 http(s) 格式
        pickup_url = (config.pickup_url or "").strip()
        if config.enabled and not pickup_url:
            return AgreeDeliverConfigResponse(
                success=False,
                message="开启同意后发货时，提货URL不能为空"
            )
        if pickup_url and not pickup_url.lower().startswith(("http://", "https://")):
            return AgreeDeliverConfigResponse(
                success=False,
                message="提货URL格式无效，必须以 http:// 或 https:// 开头"
            )

        # 管理员不限制 owner，普通用户仅能操作本人账号
        owner_id, is_admin = resolve_owner_scope(current_user)
        conditions = [XYAccount.account_id == account_id]
        if not is_admin:
            conditions.append(XYAccount.owner_id == owner_id)
        stmt = select(XYAccount).where(*conditions)
        result = await session.execute(stmt)
        account = result.scalars().first()

        if not account:
            return AgreeDeliverConfigResponse(
                success=False,
                message="账号不存在或无权限访问"
            )

        notify_message = (config.notify_message or "").strip()

        account.agree_deliver_enabled = config.enabled
        account.agree_deliver_notify_message = notify_message or None
        account.agree_deliver_pickup_url = pickup_url or None

        session.add(account)
        await session.commit()

        logger.info(f"更新账号 {account_id} 同意后发货配置: enabled={config.enabled}")

        return AgreeDeliverConfigResponse(success=True, message="同意后发货配置已更新")

    except Exception as e:
        logger.error(f"更新同意后发货配置失败: {e}")
        await session.rollback()
        return AgreeDeliverConfigResponse(
            success=False,
            message=f"更新同意后发货配置失败: {str(e)}"
        )
