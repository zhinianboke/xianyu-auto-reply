"""
退款订单注销配置路由

功能：
1. 管理账号的「退款订单注销」配置（开关、请求URL、超时时间）
2. 收到买家退款消息时，websocket 服务会按此配置调用外部注销接口
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.api import deps
from common.models.user import User
from common.models.xy_account import XYAccount
from common.utils.auth_scope import resolve_owner_scope

router = APIRouter(tags=["退款订单注销配置"])


# ==================== 请求/响应模型 ====================

class RefundCancelConfig(BaseModel):
    """退款订单注销配置"""
    enabled: bool = False  # 是否开启退款订单注销
    url: Optional[str] = None  # 注销接口请求URL
    timeout: Optional[int] = 60  # 请求超时时间(秒)，默认60秒


class RefundCancelConfigResponse(BaseModel):
    """退款订单注销配置响应"""
    success: bool
    message: str = ""
    data: Optional[RefundCancelConfig] = None


# ==================== 路由 ====================

@router.get("/{account_id}", response_model=RefundCancelConfigResponse)
async def get_refund_cancel_config(
    account_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """获取账号的退款订单注销配置（管理员可操作所有账号，普通用户仅限本人账号）"""
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
            return RefundCancelConfigResponse(
                success=False,
                message="账号不存在或无权限访问"
            )

        config = RefundCancelConfig(
            enabled=bool(account.refund_cancel_enabled),
            url=account.refund_cancel_url,
            timeout=account.refund_cancel_timeout or 60,
        )

        return RefundCancelConfigResponse(success=True, data=config)

    except Exception as e:
        logger.error(f"获取退款订单注销配置失败: {e}")
        return RefundCancelConfigResponse(
            success=False,
            message=f"获取退款订单注销配置失败: {str(e)}"
        )


@router.put("/{account_id}", response_model=RefundCancelConfigResponse)
async def update_refund_cancel_config(
    account_id: str,
    config: RefundCancelConfig,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """更新账号的退款订单注销配置"""
    try:
        # 开启时校验必要字段
        if config.enabled:
            if not config.url or not config.url.strip():
                return RefundCancelConfigResponse(
                    success=False,
                    message="开启退款订单注销时，请求URL不能为空"
                )
            if not config.url.strip().lower().startswith(("http://", "https://")):
                return RefundCancelConfigResponse(
                    success=False,
                    message="请求URL格式无效，必须以 http:// 或 https:// 开头"
                )

        # 超时校验：默认60秒，不设上限，只要求为正整数即可
        timeout = config.timeout if config.timeout is not None else 60
        if timeout < 1:
            return RefundCancelConfigResponse(
                success=False,
                message="超时时间无效，请输入大于 0 的秒数"
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
            return RefundCancelConfigResponse(
                success=False,
                message="账号不存在或无权限访问"
            )

        account.refund_cancel_enabled = config.enabled
        account.refund_cancel_url = config.url.strip() if (config.enabled and config.url) else None
        account.refund_cancel_timeout = timeout

        session.add(account)
        await session.commit()

        logger.info(f"更新账号 {account_id} 退款订单注销配置: enabled={config.enabled}")

        return RefundCancelConfigResponse(success=True, message="退款订单注销配置已更新")

    except Exception as e:
        logger.error(f"更新退款订单注销配置失败: {e}")
        await session.rollback()
        return RefundCancelConfigResponse(
            success=False,
            message=f"更新退款订单注销配置失败: {str(e)}"
        )
