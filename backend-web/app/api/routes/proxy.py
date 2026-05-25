"""
代理配置路由
管理账号的代理设置
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.api import deps
from common.models.user import User
from common.models.xy_account import XYAccount

router = APIRouter(tags=["代理配置"])


# ==================== 请求/响应模型 ====================

class ProxyConfig(BaseModel):
    """代理配置"""
    proxy_type: str = "none"  # none, http, https, socks5
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None
    proxy_user: Optional[str] = None
    proxy_pass: Optional[str] = None


class ProxyConfigResponse(BaseModel):
    """代理配置响应"""
    success: bool
    message: str = ""
    data: Optional[ProxyConfig] = None


# ==================== 路由 ====================

@router.get("/{account_id}", response_model=ProxyConfigResponse)
async def get_proxy_config(
    account_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """获取账号的代理配置"""
    try:
        # 查询账号
        stmt = select(XYAccount).where(
            XYAccount.owner_id == current_user.id,
            XYAccount.account_id == account_id,
        )
        result = await session.execute(stmt)
        account = result.scalars().first()
        
        if not account:
            return ProxyConfigResponse(
                success=False,
                message="账号不存在或无权限访问"
            )
        
        # 返回代理配置
        proxy_config = ProxyConfig(
            proxy_type=account.proxy_type or "none",
            proxy_host=account.proxy_host,
            proxy_port=account.proxy_port,
            proxy_user=account.proxy_user,
            proxy_pass=account.proxy_pass,
        )
        
        return ProxyConfigResponse(
            success=True,
            data=proxy_config
        )
        
    except Exception as e:
        logger.error(f"获取代理配置失败: {e}")
        return ProxyConfigResponse(
            success=False,
            message=f"获取代理配置失败: {str(e)}"
        )


@router.put("/{account_id}", response_model=ProxyConfigResponse)
async def update_proxy_config(
    account_id: str,
    config: ProxyConfig,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """更新账号的代理配置"""
    try:
        # 验证代理类型
        valid_proxy_types = ["none", "http", "https", "socks5"]
        if config.proxy_type not in valid_proxy_types:
            return ProxyConfigResponse(
                success=False,
                message=f"无效的代理类型，支持的类型: {', '.join(valid_proxy_types)}"
            )
        
        # 如果设置了代理类型（非none），验证必要字段
        if config.proxy_type != "none":
            if not config.proxy_host:
                return ProxyConfigResponse(
                    success=False,
                    message="代理地址不能为空"
                )
            if not config.proxy_port or config.proxy_port <= 0:
                return ProxyConfigResponse(
                    success=False,
                    message="代理端口无效"
                )
        
        # 查询账号
        stmt = select(XYAccount).where(
            XYAccount.owner_id == current_user.id,
            XYAccount.account_id == account_id,
        )
        result = await session.execute(stmt)
        account = result.scalars().first()
        
        if not account:
            return ProxyConfigResponse(
                success=False,
                message="账号不存在或无权限访问"
            )
        
        # 更新代理配置
        account.proxy_type = config.proxy_type
        account.proxy_host = config.proxy_host if config.proxy_type != "none" else None
        account.proxy_port = config.proxy_port if config.proxy_type != "none" else None
        account.proxy_user = config.proxy_user if config.proxy_type != "none" else None
        account.proxy_pass = config.proxy_pass if config.proxy_type != "none" else None
        
        session.add(account)
        await session.commit()
        
        logger.info(f"更新账号 {account_id} 代理配置: {config.proxy_type}")
        
        return ProxyConfigResponse(
            success=True,
            message="代理配置已更新"
        )
        
    except Exception as e:
        logger.error(f"更新代理配置失败: {e}")
        await session.rollback()
        return ProxyConfigResponse(
            success=False,
            message=f"更新代理配置失败: {str(e)}"
        )


@router.delete("/{account_id}", response_model=ProxyConfigResponse)
async def clear_proxy_config(
    account_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """清除账号的代理配置"""
    try:
        # 查询账号
        stmt = select(XYAccount).where(
            XYAccount.owner_id == current_user.id,
            XYAccount.account_id == account_id,
        )
        result = await session.execute(stmt)
        account = result.scalars().first()
        
        if not account:
            return ProxyConfigResponse(
                success=False,
                message="账号不存在或无权限访问"
            )
        
        # 清除代理配置
        account.proxy_type = "none"
        account.proxy_host = None
        account.proxy_port = None
        account.proxy_user = None
        account.proxy_pass = None
        
        session.add(account)
        await session.commit()
        
        logger.info(f"清除账号 {account_id} 代理配置")
        
        return ProxyConfigResponse(
            success=True,
            message="代理配置已清除"
        )
        
    except Exception as e:
        logger.error(f"清除代理配置失败: {e}")
        await session.rollback()
        return ProxyConfigResponse(
            success=False,
            message=f"清除代理配置失败: {str(e)}"
        )
