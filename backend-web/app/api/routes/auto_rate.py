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
from loguru import logger
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
    # 好评后自动发送消息（#232）
    thanks_enabled: bool = False
    thanks_content: str | None = None


class AutoRateConfigUpdate(BaseModel):
    """自动评价配置更新"""
    enabled: bool = False
    rate_type: str = "text"
    text_content: str | None = None
    api_url: str | None = None
    # 好评后自动发送消息（#232）
    thanks_enabled: bool = False
    thanks_content: str | None = None


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
                thanks_enabled=bool(config.thanks_enabled),
                thanks_content=config.thanks_content,
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
                thanks_enabled=False,
                thanks_content=None,
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
    
    # 好评后消息（#232）：开启时必须填写内容；未开启时清空内容避免残留
    thanks_content = (config_update.thanks_content or "").strip() or None
    if config_update.thanks_enabled:
        if not thanks_content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请填写好评后发送的消息内容")
    else:
        thanks_content = None
    
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
        config.thanks_enabled = config_update.thanks_enabled
        config.thanks_content = thanks_content
    else:
        # 创建
        config = AutoRateConfig(
            account_id=account_id,
            enabled=config_update.enabled,
            rate_type=config_update.rate_type,
            text_content=config_update.text_content,
            api_url=config_update.api_url,
            thanks_enabled=config_update.thanks_enabled,
            thanks_content=thanks_content,
        )
        db.add(config)

    await db.commit()

    return ApiResponse(success=True, message="保存成功")


async def _send_thanks_after_rate(db: AsyncSession, account_id: str, order_id: str) -> None:
    """批量补评价成功后自动向买家发送配置的致谢消息（#232）

    与 websocket 实时评价、定时补评价路径共用订单 is_thanks_sent 标记去重；
    任何失败仅记录日志，不影响批量评价结果。
    """
    try:
        from common.models.xy_order import XYOrder
        from common.services.rate_service import (
            get_thanks_message_content, is_order_thanks_sent, mark_order_thanks_sent,
        )
        from app.services.websocket_client import websocket_client

        content = await get_thanks_message_content(account_id)
        if not content:
            return
        if await is_order_thanks_sent(order_id):
            return

        stmt = select(XYOrder).where(XYOrder.order_no == order_id)
        result = await db.execute(stmt)
        order = result.scalars().first()
        if not order or not order.buyer_id or not order.item_id:
            logger.warning(f"[批量补评价] 订单 {order_id} 缺少买家/商品信息，跳过好评后消息")
            return

        create_result = await websocket_client.create_chat(
            account_id=account_id,
            buyer_id=str(order.buyer_id),
            item_id=str(order.item_id),
        )
        if not isinstance(create_result, dict) or not create_result.get("success"):
            logger.warning(f"[批量补评价] 订单 {order_id} 创建会话失败，跳过好评后消息")
            return
        chat_id = (create_result.get("data") or {}).get("chat_id")
        if not chat_id:
            logger.warning(f"[批量补评价] 订单 {order_id} 创建会话响应缺少 chat_id，跳过好评后消息")
            return

        # 直接按内部接口契约发送（websocket_client.send_message 的字段与内部接口不一致，见 #326）
        # to_user_id 为 #326 起的必填项：缺省会导致接收人变成 None@goofish，买家收不到
        send_res = await websocket_client.http_client.post(
            f"{websocket_client.base_url}/internal/accounts/{account_id}/send-message",
            json={
                "chat_id": chat_id,
                "message": content,
                "to_user_id": str(order.buyer_id),
                "wait_result": True,
            },
        )
        if not isinstance(send_res, dict) or not send_res.get("success"):
            logger.warning(f"[批量补评价] 订单 {order_id} 好评后消息发送失败: {send_res}")
            return

        data = send_res.get("data") or {}
        if (data.get("send_status") or "unknown") == "failed":
            logger.warning(
                f"[批量补评价] 订单 {order_id} 好评后消息被拦截: {data.get('send_fail_reason')}"
            )
            return

        await mark_order_thanks_sent(order_id)
        logger.info(f"[批量补评价] 订单 {order_id} 好评后消息已发送")
    except Exception as e:
        logger.warning(f"[批量补评价] 订单 {order_id} 好评后消息发送异常: {e}")


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
                        # 好评后自动发送致谢消息（#232），失败不影响批量评价结果
                        await _send_thanks_after_rate(db, account_id, order_id)
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
