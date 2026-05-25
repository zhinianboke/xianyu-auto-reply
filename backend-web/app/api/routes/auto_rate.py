"""
自动评价配置API

功能：
1. 获取自动评价配置
2. 更新自动评价配置
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models.user import User
from common.models.auto_rate_config import AutoRateConfig
from common.schemas.common import ApiResponse
from common.utils.auth_scope import resolve_owner_scope
from app.services.account_service import AccountService

router = APIRouter(tags=["auto-rate"])


class AutoRateConfigOut(BaseModel):
    """自动评价配置输出"""
    account_id: str
    enabled: bool = False
    rate_type: str = "text"  # text 或 api
    text_content: str | None = None
    api_url: str | None = None


class AutoRateConfigUpdate(BaseModel):
    """自动评价配置更新"""
    enabled: bool = False
    rate_type: str = "text"
    text_content: str | None = None
    api_url: str | None = None


@router.get("/{account_id}")
async def get_auto_rate_config(
    account_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    db: AsyncSession = Depends(deps.get_db_session),
):
    """获取账号的自动评价配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    
    # 查询配置
    stmt = select(AutoRateConfig).where(AutoRateConfig.account_id == account_id)
    result = await db.execute(stmt)
    config = result.scalars().first()
    
    if config:
        return {
            "success": True,
            "data": AutoRateConfigOut(
                account_id=config.account_id,
                enabled=config.enabled,
                rate_type=config.rate_type or "text",
                text_content=config.text_content,
                api_url=config.api_url,
            )
        }
    else:
        # 返回默认配置
        return {
            "success": True,
            "data": AutoRateConfigOut(
                account_id=account_id,
                enabled=False,
                rate_type="text",
                text_content="不错的买家",
                api_url=None,
            )
        }


@router.put("/{account_id}")
async def update_auto_rate_config(
    account_id: str,
    config_update: AutoRateConfigUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    db: AsyncSession = Depends(deps.get_db_session),
):
    """更新账号的自动评价配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    
    # 验证参数
    if config_update.rate_type not in ["text", "api"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="评价类型无效")
    
    if config_update.enabled:
        if config_update.rate_type == "text" and not config_update.text_content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请填写评价内容")
        if config_update.rate_type == "api" and not config_update.api_url:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请填写API地址")
    
    # 查询或创建配置
    stmt = select(AutoRateConfig).where(AutoRateConfig.account_id == account_id)
    result = await db.execute(stmt)
    config = result.scalars().first()
    
    if config:
        # 更新
        config.enabled = config_update.enabled
        config.rate_type = config_update.rate_type
        config.text_content = config_update.text_content
        config.api_url = config_update.api_url
    else:
        # 创建
        config = AutoRateConfig(
            account_id=account_id,
            enabled=config_update.enabled,
            rate_type=config_update.rate_type,
            text_content=config_update.text_content,
            api_url=config_update.api_url,
        )
        db.add(config)

    await db.commit()

    return ApiResponse(success=True, message="保存成功")
