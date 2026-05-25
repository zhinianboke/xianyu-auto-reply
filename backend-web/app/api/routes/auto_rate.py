"""
自动评价配置API

功能：
1. 获取自动评价配置
2. 更新自动评价配置
3. 批量订单补评价
"""
from __future__ import annotations

import asyncio
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models.user import User
from common.models.auto_rate_config import AutoRateConfig
from common.models.xy_account import XYAccount
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


class BatchRateRequest(BaseModel):
    """批量补评价请求"""
    account_ids: List[str]


@router.post("/batch-rate")
async def batch_rate_orders(
    request: BatchRateRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    db: AsyncSession = Depends(deps.get_db_session),
):
    """批量订单补评价
    
    对选中的账号执行补评价操作：
    1. 检查账号是否启用了自动评价
    2. 调用闲鱼接口获取待评价订单列表
    3. 逐个执行评价（每笔间隔1秒）
    """
    from loguru import logger
    from common.services.rate_service import (
        RateService, fetch_merchant_rate_list, get_rate_feedback_content
    )
    
    if not request.account_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择账号")
    
    owner_id, _ = resolve_owner_scope(current_user)
    
    # 去重
    account_ids = list(dict.fromkeys(
        aid.strip() for aid in request.account_ids if aid and aid.strip()
    ))
    
    results = []
    
    for account_id in account_ids:
        account_result = {
            "account_id": account_id,
            "success": False,
            "rated_count": 0,
            "failed_count": 0,
            "total_pending": 0,
            "message": "",
        }
        
        try:
            # 验证账号归属
            account = await account_service.get_account_for_user(owner_id, account_id)
            if not account:
                account_result["message"] = "账号不存在或无权限"
                results.append(account_result)
                continue
            
            # 检查是否启用了自动评价
            stmt = select(AutoRateConfig).where(
                AutoRateConfig.account_id == account_id,
                AutoRateConfig.enabled == True,
            )
            config_result = await db.execute(stmt)
            rate_config = config_result.scalars().first()
            
            if not rate_config:
                account_result["message"] = "未启用自动评价"
                results.append(account_result)
                continue
            
            # 检查Cookie
            if not account.cookie:
                account_result["message"] = "账号无Cookie"
                results.append(account_result)
                continue
            
            # 获取评价内容
            feedback = await get_rate_feedback_content(account_id)
            if not feedback:
                account_result["message"] = "获取评价内容失败"
                results.append(account_result)
                continue
            
            # 获取待评价订单列表（带重试）
            list_result = await fetch_merchant_rate_list(
                cookie_string=account.cookie,
                account_id=account_id,
                page=1,
                page_size=100,
                max_retries=3,
            )
            
            if not list_result['success']:
                account_result["message"] = f"获取待评价列表失败: {list_result['message']}"
                results.append(account_result)
                continue
            
            pending_items = list_result['items']
            account_result["total_pending"] = len(pending_items)
            
            if not pending_items:
                account_result["success"] = True
                account_result["message"] = "没有待评价订单"
                results.append(account_result)
                continue
            
            # 使用可能刷新后的cookie
            current_cookie = list_result['cookies_str']
            
            # 逐个评价，每笔间隔1秒
            for item in pending_items:
                order_id = item.get('merchantCommonData', {}).get('orderId')
                if not order_id:
                    account_result["failed_count"] += 1
                    continue
                
                try:
                    rate_service = RateService(current_cookie, account_id=account_id)
                    rate_result = await rate_service.rate_buyer(order_id, feedback=feedback)
                    
                    # 如果cookie被刷新了，更新本地变量
                    if rate_service.cookie_string != current_cookie:
                        current_cookie = rate_service.cookie_string
                    
                    if rate_result.get('success'):
                        account_result["rated_count"] += 1
                    else:
                        account_result["failed_count"] += 1
                        logger.warning(
                            f"[批量补评价] 账号 {account_id} 订单 {order_id} "
                            f"评价失败: {rate_result.get('message')}"
                        )
                except Exception as e:
                    account_result["failed_count"] += 1
                    logger.error(
                        f"[批量补评价] 账号 {account_id} 订单 {order_id} 异常: {e}"
                    )
                
                # 每笔间隔1秒
                await asyncio.sleep(1)
            
            account_result["success"] = True
            rated = account_result["rated_count"]
            failed = account_result["failed_count"]
            account_result["message"] = f"评价完成: 成功 {rated} 笔，失败 {failed} 笔"
            
        except Exception as e:
            account_result["message"] = f"处理异常: {str(e)}"
            logger.error(f"[批量补评价] 账号 {account_id} 处理异常: {e}")
        
        results.append(account_result)
    
    # 汇总
    total_rated = sum(r["rated_count"] for r in results)
    total_failed = sum(r["failed_count"] for r in results)
    success_accounts = sum(1 for r in results if r["success"])
    
    return ApiResponse(
        success=True,
        message=f"批量补评价完成: {success_accounts}/{len(account_ids)} 个账号处理成功，共评价 {total_rated} 笔订单",
        data={
            "total_rated": total_rated,
            "total_failed": total_failed,
            "success_accounts": success_accounts,
            "total_accounts": len(account_ids),
            "details": results,
        },
    )
