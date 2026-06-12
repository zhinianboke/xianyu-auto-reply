"""
WebSocket服务内部API路由

功能：
1. 提供账号任务管理接口(启动/停止/重启)
2. 提供任务状态查询接口
3. 提供消息发送接口
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/internal", tags=["internal"])


class StartAccountRequest(BaseModel):
    """启动账号请求"""
    cookie_value: str | None = None  # 可选，不传则从数据库获取
    user_id: int | None = None


class SendMessageRequest(BaseModel):
    """发送消息请求"""
    chat_id: str
    message: str


class DeliverOrderRequest(BaseModel):
    """订单发货请求"""
    order_no: str
    item_id: str
    buyer_id: str
    chat_id: str
    card_id: int
    is_bargain: bool = False
    delivery_method: str = "auto"  # 发货方式：auto-自动发货，manual-手动发货，scheduled-定时补发货
    # 订单数量：>1 时接口会按数量循环获取并发送 N 张卡券（与自动发货 multi_quantity_delivery 语义对齐）。
    # 默认为 1 保持旧调用方零成本兼容；调用方应该按订单实际 quantity 字段（XYOrder.quantity）传入。
    quantity: int = 1


class ConfirmNoLogisticsRequest(BaseModel):
    account_id: str
    order_no: str
    item_id: str
    buyer_id: str = ""
    is_bargain: bool = False


class CancelOrderRequest(BaseModel):
    account_id: str
    order_no: str


class CreateChatRequest(BaseModel):
    """创建单聊会话请求
    
    通过 LWP 协议 /r/SingleChatConversation/create 创建或获取会话。
    服务端按 (pairFirst, pairSecond, bizType) 幂等生成 cid，已存在则直接返回现有 cid。
    """
    buyer_id: str  # 对方用户ID（买家ID），不带 @goofish 后缀
    item_id: str   # 关联商品ID


class LogRetentionRequest(BaseModel):
    """日志保留天数刷新请求"""
    retention_days: int


@router.post("/logs/retention")
async def refresh_log_retention(request: LogRetentionRequest):
    """实时刷新日志保留天数"""
    try:
        from common.utils.logging_utils import update_log_retention

        updated = update_log_retention(request.retention_days)
        return {
            "success": True,
            "code": 200,
            "message": "日志保留天数已刷新" if updated else "日志保留天数无需变更",
            "data": {
                "retention_days": request.retention_days,
                "updated": updated,
            },
        }
    except Exception as e:
        return {
            "success": False,
            "code": 500,
            "message": f"日志保留天数刷新失败: {str(e)}",
            "data": None,
        }


@router.post("/accounts/{account_id}/start")
async def start_account(account_id: str, request: StartAccountRequest = None):
    """
    启动账号任务
    
    Args:
        account_id: 账号ID
        request: 启动请求参数(可选)
        
    Returns:
        操作结果
    """
    try:
        from app.services.xianyu.cookie_manager import get_manager
        from loguru import logger
        
        manager = get_manager()
        
        # 如果没有传递 cookie_value，从数据库获取
        cookie_value = None
        user_id = None
        if request:
            cookie_value = request.cookie_value
            user_id = request.user_id
        
        if not cookie_value:
            # 从数据库获取 cookie
            from common.db.session import async_session_maker
            from common.models import XYAccount
            from sqlalchemy import select
            
            async with async_session_maker() as session:
                result = await session.execute(
                    select(XYAccount).where(XYAccount.account_id == account_id)
                )
                account = result.scalars().first()
                if account:
                    cookie_value = account.cookie
                    user_id = account.owner_id
        
        if not cookie_value:
            return {
                "success": False,
                "code": 400,
                "message": f"账号 {account_id} 未找到有效的Cookie",
                "data": None,
            }
        
        # 更新内存中的数据
        manager.cookies[account_id] = cookie_value
        manager.cookie_status[account_id] = True
        manager.keywords.setdefault(account_id, [])
        manager.auto_confirm_settings.setdefault(account_id, True)
        
        # 直接调用异步方法启动任务
        await manager._add_cookie_async(account_id, cookie_value, user_id)
        
        logger.info(f"账号任务启动成功: {account_id}")
        
        return {
            "success": True,
            "code": 200,
            "message": "账号任务启动成功",
            "data": {
                "account_id": account_id,
                "status": "starting",
            },
        }
    except Exception as e:
        from loguru import logger
        import traceback
        logger.error(f"启动账号任务失败: {account_id}, 错误: {e}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "code": 500,
            "message": f"启动账号任务失败: {str(e)}",
            "data": None,
        }


@router.post("/accounts/{account_id}/stop")
async def stop_account(account_id: str):
    """
    停止账号任务
    
    Args:
        account_id: 账号ID
        
    Returns:
        操作结果
    """
    try:
        from app.services.xianyu.cookie_manager import get_manager
        from loguru import logger
        
        manager = get_manager()
        manager.remove_cookie(account_id)
        logger.info(f"账号任务停止成功: {account_id}")
        
        return {
            "success": True,
            "code": 200,
            "message": "账号任务停止成功",
            "data": {
                "account_id": account_id,
                "status": "stopped",
            },
        }
    except Exception as e:
        return {
            "success": False,
            "code": 500,
            "message": f"停止账号任务失败: {str(e)}",
            "data": None,
        }


@router.post("/accounts/{account_id}/restart")
async def restart_account(account_id: str, request: StartAccountRequest):
    """
    重启账号任务
    
    Args:
        account_id: 账号ID
        request: 启动请求参数
        
    Returns:
        操作结果
    """
    try:
        from app.services.xianyu.cookie_manager import get_manager
        from loguru import logger
        
        # 重启前清除Token缓存，确保重新获取Token和完整Cookie
        # 注意：xy_token_cache.user_id 存的是闲鱼的 unb（myid），不是 cookie_id(account_id)
        # 因此必须先从 Cookie 中解析出 unb 再作为 user_id 参数删除
        try:
            from common.db.session import async_session_maker
            from common.utils.cookie_refresh import get_account_by_identity
            from common.utils.xianyu_utils import trans_cookies
            from sqlalchemy import text

            # 1) 优先用请求携带的 cookie_value，其次回退数据库查询
            cookie_str = request.cookie_value
            if not cookie_str:
                try:
                    account = await get_account_by_identity(
                        account_id,
                        owner_id=request.user_id,
                    )
                    cookie_str = account.cookie if account else None
                except Exception as query_e:
                    logger.warning(f"查询账号Cookie用于清除Token缓存失败: {query_e}")
                    cookie_str = None

            # 2) 解析 unb
            unb = ""
            if cookie_str:
                try:
                    cookies_dict = trans_cookies(cookie_str) or {}
                    unb = cookies_dict.get("unb", "") or ""
                except Exception as parse_e:
                    logger.warning(f"解析Cookie获取unb失败: {parse_e}")
                    unb = ""

            # 3) 用正确的 unb 作为 user_id 删除 Token 缓存
            if unb:
                async with async_session_maker() as session:
                    await session.execute(
                        text("DELETE FROM xy_token_cache WHERE user_id = :user_id"),
                        {"user_id": unb},
                    )
                    await session.commit()
                    logger.info(f"账号重启前已清除Token缓存: account_id={account_id}, user_id={unb}")
            else:
                logger.warning(f"未能解析出unb，跳过Token缓存清除: account_id={account_id}")
        except Exception as cache_e:
            logger.warning(f"清除Token缓存失败(不影响重启): {cache_e}")
        
        manager = get_manager()
        # 先停止
        manager.remove_cookie(account_id)
        # 再启动
        manager.add_cookie(
            cookie_id=account_id,
            cookie_value=request.cookie_value,
            user_id=request.user_id
        )
        logger.info(f"账号任务重启成功: {account_id}")
        
        return {
            "success": True,
            "code": 200,
            "message": "账号任务重启成功",
            "data": {
                "account_id": account_id,
                "status": "restarting",
            },
        }
    except Exception as e:
        return {
            "success": False,
            "code": 500,
            "message": f"重启账号任务失败: {str(e)}",
            "data": None,
        }


@router.get("/accounts/connection-stats")
async def get_connection_stats():
    """统计真实 WebSocket 连接状态（已连接账号数量等）"""
    try:
        from app.services.xianyu.cookie_manager import get_manager

        manager = get_manager()
        stats = manager.get_connection_stats()

        return {
            "success": True,
            "code": 200,
            "message": "查询成功",
            "data": stats,
        }
    except Exception as e:
        return {
            "success": False,
            "code": 500,
            "message": f"查询连接统计失败: {str(e)}",
            "data": None,
        }


@router.get("/accounts/{account_id}/status")
async def get_account_status(account_id: str):
    """
    查询账号任务状态

    Args:
        account_id: 账号ID
        
    Returns:
        任务状态信息
    """
    try:
        from app.services.xianyu.cookie_manager import get_manager
        
        manager = get_manager()
        status = manager.get_task_status(account_id)
        
        return {
            "success": True,
            "code": 200,
            "message": "查询成功",
            "data": {
                "account_id": account_id,
                **status
            },
        }
    except Exception as e:
        return {
            "success": False,
            "code": 500,
            "message": f"查询账号状态失败: {str(e)}",
            "data": None,
        }


@router.post("/accounts/{account_id}/send-message")
async def send_message(account_id: str, request: SendMessageRequest):
    """
    发送消息
    
    Args:
        account_id: 账号ID
        request: 消息请求参数
        
    Returns:
        操作结果
    """
    try:
        from app.services.xianyu.cookie_manager import get_manager
        from loguru import logger
        
        manager = get_manager()
        
        # 获取账号实例
        instance = manager.instances.get(account_id)
        if not instance:
            return {
                "success": False,
                "code": 404,
                "message": f"账号 {account_id} 未运行或不存在",
                "data": None,
            }
        
        # 检查是否有 WebSocket 连接
        if not hasattr(instance, 'ws') or not instance.ws:
            return {
                "success": False,
                "code": 400,
                "message": f"账号 {account_id} WebSocket 未连接",
                "data": None,
            }
        
        # 发送消息
        await instance.send_msg(
            websocket=instance.ws,
            chat_id=request.chat_id,
            send_user_id=None,  # 由实例内部获取
            content=request.message
        )
        
        logger.info(f"【{account_id}】消息发送成功: chat_id={request.chat_id}")
        
        return {
            "success": True,
            "code": 200,
            "message": "消息发送成功",
            "data": {
                "account_id": account_id,
                "chat_id": request.chat_id,
                "message": request.message,
            },
        }
    except Exception as e:
        return {
            "success": False,
            "code": 500,
            "message": f"发送消息失败: {str(e)}",
            "data": None,
        }


@router.post("/orders/confirm-no-logistics")
async def confirm_no_logistics(request: ConfirmNoLogisticsRequest):
    """无物流发货：在闲鱼确认发货但不发送任何卡券内容"""
    from app.services.xianyu.cookie_manager import get_manager
    from common.db.session import async_session_maker
    from common.services.order_service import OrderService

    xianyu_live = get_manager().instances.get(request.account_id)
    if not xianyu_live:
        return {"success": False, "code": 404, "message": "账号未连接", "data": None}

    if request.is_bargain:
        result = await xianyu_live.auto_delivery_handler.auto_freeshipping(
            request.order_no, request.item_id, request.buyer_id
        )
    else:
        result = await xianyu_live.auto_delivery_handler.auto_confirm(
            request.order_no, request.item_id
        )

    if not result or not result.get("success"):
        message = (result or {}).get("error") or (result or {}).get("message") or "无物流发货失败"
        return {"success": False, "code": 400, "message": message, "data": result}

    async with async_session_maker() as session:
        await OrderService(session).update_order_delivery_info(
            request.order_no,
            status="shipped",
            delivery_method="manual",
            delivery_content="无物流发货",
        )

    return {"success": True, "code": 200, "message": "无物流发货成功", "data": result}


@router.post("/orders/cancel")
async def cancel_order(request: CancelOrderRequest):
    """卖家关闭（取消）订单"""
    from app.services.xianyu.cookie_manager import get_manager
    from common.db.session import async_session_maker
    from common.models import XYOrder
    from sqlalchemy import update

    xianyu_live = get_manager().instances.get(request.account_id)
    if not xianyu_live:
        return {"success": False, "code": 404, "message": "账号未连接", "data": None}

    closed = await xianyu_live.auto_delivery_handler.close_order_by_seller(request.order_no)
    if not closed:
        return {"success": False, "code": 400, "message": "取消订单失败，请检查闲鱼订单状态", "data": None}

    async with async_session_maker() as session:
        await session.execute(
            update(XYOrder).where(XYOrder.order_no == request.order_no).values(status="cancelled")
        )
        await session.commit()
    return {"success": True, "code": 200, "message": "订单已取消", "data": {"order_no": request.order_no}}


@router.post("/orders/deliver")
async def deliver_order(request: DeliverOrderRequest):
    """
    订单发货接口
    
    处理订单发货逻辑：
    1. 获取 XianyuLive 实例
    2. 调用确认发货接口（auto_confirm）
    3. 如果是小刀订单，调用免拼接口（auto_freeshipping）
    4. 根据卡券类型获取发货内容（text/data/image/api）
    5. 发送消息给买家
    6. 更新卡券发货次数
    7. 返回发货结果
    
    Args:
        request: 发货请求参数
        
    Returns:
        操作结果
    """
    try:
        from app.services.xianyu.cookie_manager import get_manager
        from loguru import logger
        from common.db.compat import db_manager
        from common.db.session import async_session_maker
        from sqlalchemy import select
        from common.models.card import Card
        
        logger.info(f"【内部API】收到订单发货请求: order_no={request.order_no}, 发货方式={request.delivery_method}")
        
        # 根据订单号获取账号ID
        order_info = db_manager.get_order_by_id(request.order_no)
        
        if not order_info:
            raise HTTPException(
                status_code=404,
                detail=f"订单不存在: {request.order_no}"
            )
        
        # 检查订单金额，金额为0禁止发货
        order_amount = order_info.get('amount')
        if order_amount is not None:
            from decimal import Decimal
            if Decimal(str(order_amount)) <= 0:
                logger.warning(f"【内部API】❌ 订单 {request.order_no} 金额为 {order_amount}，禁止发货")
                return {
                    "success": False,
                    "code": 400,
                    "message": "订单金额为0，禁止发货",
                    "data": None
                }

        account_id = order_info.get('account_id')
        if not account_id:
            raise HTTPException(
                status_code=400,
                detail="订单缺少账号信息"
            )
        
        # 获取 CookieManager 实例
        manager = get_manager()
        xianyu_live = manager.instances.get(account_id)
        
        if not xianyu_live:
            raise HTTPException(
                status_code=404,
                detail=f"账号 {account_id} 未启动或不存在"
            )
        
        # 获取 WebSocket 连接
        ws = xianyu_live.ws
        if not ws:
            logger.error(f"【内部API】账号 {account_id} 的 WebSocket 未连接")
            return {
                "success": False,
                "code": 503,
                "message": "WebSocket 未连接",
                "data": None
            }
        
        # 验证商品是否属于当前账号
        if request.item_id:
            from common.db.session import async_session_maker
            from sqlalchemy import select
            from common.models.xy_catalog_item import XYCatalogItem
            from common.models.xy_account import XYAccount
            
            async with async_session_maker() as session:
                # 先查询账号获取 account_pk
                account_stmt = select(XYAccount).where(XYAccount.account_id == account_id)
                account_result = await session.execute(account_stmt)
                account = account_result.scalars().first()
                
                if not account:
                    logger.error(f"【内部API】账号 {account_id} 不存在")
                    return {
                        "success": False,
                        "code": 404,
                        "message": f"账号 {account_id} 不存在",
                        "data": None
                    }
                
                # 查询商品是否属于该账号
                stmt = select(XYCatalogItem).where(
                    XYCatalogItem.item_id == request.item_id,
                    XYCatalogItem.account_pk == account.id
                )
                result = await session.execute(stmt)
                item = result.scalars().first()
                
                if not item:
                    logger.warning(
                        f"【内部API】商品 {request.item_id} 不属于账号 {account_id}，"
                        f"跳过发货（account_pk={account.id}）"
                    )
                    return {
                        "success": False,
                        "code": 400,
                        "message": f"商品 {request.item_id} 不属于当前账号",
                        "data": None
                    }
        
        # 禁止发货统一拦截：调用 auto_delivery_handler.pre_delivery_check_and_close
        # 完成"取设置→评价检查→命中后发消息+写 fail_reason+按开关关闭订单"全部链路。
        # 返回的 action 决定后续行为：
        #   'allow'     → 正常发货（含 confirm + 免拼 + 卡券）
        #   'block'     → 拦截：以 ApiResponse 返回给调用方
        #   'card_only' → 跳过 confirm 和免拼接口，直接进入卡券发货流程（订单已被关闭）
        pre_check = await xianyu_live.auto_delivery_handler.pre_delivery_check_and_close(
            websocket=ws,
            order_no=request.order_no,
            buyer_id=request.buyer_id,
            chat_id=request.chat_id,
            log_prefix="【内部API】",
            item_id=request.item_id,
        )
        pre_check_action = pre_check.get('action', 'allow')
        if pre_check_action == 'block':
            return {
                "success": False,
                "code": 200,
                "message": pre_check['fail_record'],
                "data": {
                    "order_no": request.order_no,
                    "delivery_blocked": True,
                    "buyer_total_count": 0,
                    "auto_close_enabled": pre_check['auto_close_enabled'],
                    "order_closed": pre_check['order_closed'],
                },
            }
        # card_only：跳过 confirm + 免拼接口，仅发卡券（订单已被卖家主动关闭）
        skip_confirm_for_card_only = (pre_check_action == 'card_only')

        # 检查是否开启"卡券发送成功再确认发货"模式
        send_before_confirm_mode = False
        if not skip_confirm_for_card_only:
            try:
                send_before_confirm_mode = db_manager.get_send_before_confirm(account_id)
            except Exception as e:
                logger.warning(f"【内部API】获取卡券发送成功再确认发货设置异常: {e}")

        # 调用确认发货接口
        order_already_shipped = False  # 标记订单是否已发货

        if skip_confirm_for_card_only:
            logger.info(
                f"【内部API】card_only 模式：跳过确认发货 + 免拼接口，仅发送卡券: "
                f"order_no={request.order_no}"
            )
        elif send_before_confirm_mode:
            # send_before_confirm 模式前提：自动确认发货必须开启
            if not xianyu_live.is_auto_confirm_enabled():
                logger.warning(f"【内部API】自动确认发货已关闭，且卡券发送成功再确认发货开关已开启，不发送卡券: {request.order_no}")
                return {
                    "success": False,
                    "code": 200,
                    "message": "自动确认发货已关闭，无法执行发货流程",
                    "data": None,
                }
            logger.info(
                f"【内部API】send_before_confirm 模式：先发卡券再确认发货，跳过此处确认: "
                f"order_no={request.order_no}"
            )
        elif xianyu_live.is_auto_confirm_enabled():
            logger.info(f"【内部API】开始确认发货: order_no={request.order_no}")
            confirm_result = await xianyu_live.auto_delivery_handler.auto_confirm(
                order_id=request.order_no,
                item_id=request.item_id
            )
            
            if confirm_result and confirm_result.get('success'):
                # 检查是否是"已发货成功"的响应
                success_msg = confirm_result.get('message', '')
                if 'ORDER_ALREADY_DELIVERY' in success_msg or '已发货成功' in success_msg:
                    logger.info(f"【内部API】订单 {request.order_no} 已发货过，只更新数据库状态，不再发送卡券")
                    order_already_shipped = True
                else:
                    logger.info(f"【内部API】确认发货成功: order_no={request.order_no}")
            else:
                error_msg = confirm_result.get('error', '未知错误') if confirm_result else '未知错误'
                # 如果是已发货，也标记为已发货
                if 'ORDER_ALREADY_DELIVERY' in error_msg or '已发货成功' in error_msg:
                    logger.info(f"【内部API】订单 {request.order_no} 已发货过，只更新数据库状态，不再发送卡券")
                    order_already_shipped = True
                else:
                    logger.warning(f"【内部API】确认发货失败: {error_msg}")
                    # 检查"发货成功再发卡券"开关，如果开启则不发送卡券
                    try:
                        if db_manager.get_confirm_before_send(account_id):
                            logger.warning(f"【内部API】发货成功再发卡券开关已开启，确认发货失败，不发送卡券: {request.order_no}")
                            return {
                                "success": False,
                                "code": 200,
                                "message": f"确认发货失败，已跳过发送卡券: {error_msg}",
                                "data": None,
                            }
                    except Exception as e:
                        logger.warning(f"【内部API】获取发货成功再发卡券设置异常: {e}")
        else:
            logger.info(f"【内部API】自动确认发货已关闭，跳过确认发货")

        # 如果是小刀订单，调用免拼接口（card_only 模式和 send_before_confirm 模式下跳过）
        if request.is_bargain and not order_already_shipped and not skip_confirm_for_card_only and not send_before_confirm_mode:
            logger.info(f"【内部API】检测到小刀订单，调用免拼发货接口: order_no={request.order_no}")
            freeshipping_result = await xianyu_live.auto_delivery_handler.auto_freeshipping(
                order_id=request.order_no,
                item_id=request.item_id,
                buyer_id=request.buyer_id
            )
            
            if freeshipping_result and freeshipping_result.get('success'):
                # 检查是否是"已发货成功"的响应
                success_msg = freeshipping_result.get('message', '')
                if 'ORDER_ALREADY_DELIVERY' in success_msg or '已发货成功' in success_msg:
                    logger.info(f"【内部API】订单 {request.order_no} 免拼已发货过，只更新数据库状态，不再发送卡券")
                    order_already_shipped = True
                else:
                    logger.info(f"【内部API】免拼发货成功: order_no={request.order_no}")
            else:
                error_msg = freeshipping_result.get('error', '未知错误') if freeshipping_result else '未知错误'
                # 如果是已发货，也标记为已发货
                if 'ORDER_ALREADY_DELIVERY' in error_msg or '已发货成功' in error_msg:
                    logger.info(f"【内部API】订单 {request.order_no} 免拼已发货过，只更新数据库状态，不再发送卡券")
                    order_already_shipped = True
                else:
                    logger.warning(f"【内部API】免拼发货失败: {error_msg}")
                    # 检查"发货成功再发卡券"开关，如果开启则不发送卡券
                    try:
                        if db_manager.get_confirm_before_send(account_id):
                            logger.warning(f"【内部API】发货成功再发卡券开关已开启，免拼发货失败，不发送卡券: {request.order_no}")
                            return {
                                "success": False,
                                "code": 200,
                                "message": f"免拼发货失败，已跳过发送卡券: {error_msg}",
                                "data": None,
                            }
                    except Exception as e:
                        logger.warning(f"【内部API】获取发货成功再发卡券设置异常: {e}")
        
        # 如果订单已发货，只返回状态同步结果，不发送卡券
        if order_already_shipped:
            return {
                "success": True,
                "code": 200,
                "message": "订单已发货，状态已同步",
                "data": {
                    "order_no": request.order_no,
                    "already_shipped": True,
                    "delivery_content": "订单已确认发货（闲鱼平台已发货）",
                    "delivery_method": request.delivery_method
                }
            }
        
        # 获取卡券信息及对接关系
        card_source = 'own'
        dock_record_id = None
        async with async_session_maker() as session:
            stmt = select(Card).where(Card.id == request.card_id)
            result = await session.execute(stmt)
            card = result.scalars().first()
            
            if not card:
                logger.error(f"【内部API】未找到卡券: card_id={request.card_id}")
                return {
                    "success": False,
                    "code": 404,
                    "message": f"卡券 {request.card_id} 不存在",
                    "data": None
                }
            
            # 查询卡券的对接关系（card_source 和 dock_record_id）
            from common.models.card_item_relation import CardItemRelation
            rel_stmt = select(CardItemRelation.source, CardItemRelation.dock_record_id).where(
                CardItemRelation.card_id == request.card_id,
                CardItemRelation.item_id == request.item_id,
            )
            rel_result = await session.execute(rel_stmt)
            rel_row = rel_result.first()
            if rel_row:
                card_source = rel_row[0] or 'own'
                dock_record_id = rel_row[1]
        
        # card_only 模式（禁止发货 + 主动关闭订单 + 仅发卡券）下，对接卡券会让货主双重亏损：
        #   - 闲鱼订单被关闭 → 买家拿到全额退款
        #   - 但 _create_agent_order 仍会扣货主对接账户余额并分润给上下级代理
        # 为避免这种意外财务损失，对接卡券一律不走 card_only 流程，等同于 block：
        # 订单已被关闭，但卡券不发送。
        #
        # 注意：返回 success=True 而非 False，理由：
        #   1) pre_check 已成功执行（关闭订单 + 写 fail_reason + 通知买家），业务流程已合理处理；
        #   2) 若返回 success=False，调用方（backend-web/orders.py、redelivery_task.py）会
        #      调 update_order_delivery_fail_reason 覆盖 pre_check 写入的"禁止发货原因"，
        #      并触发 backend-web 抛 HTTPException 500；
        #   3) is_card_only=True 已让调用方跳过 status='shipped' 强制覆盖；
        #   4) skipped_due_to_dock_card=True 让调用方区分"卡券实际未发送"的特殊场景。
        if skip_confirm_for_card_only and card_source in ('dock_l1', 'dock_l2'):
            logger.warning(
                f"【内部API】card_only 模式 + 对接卡券：跳过卡券发送（订单已被关闭，避免货主财务损失），"
                f"order_no={request.order_no}, card_source={card_source}"
            )
            return {
                "success": True,
                "code": 200,
                "message": "card_only 模式不适用于对接卡券，订单已关闭但未发送卡券（避免货主财务损失，请使用自有卡券）",
                "data": {
                    "order_no": request.order_no,
                    "delivery_method": request.delivery_method,
                    "is_card_only": True,
                    # 标识：因对接卡券保护而跳过发送，调用方据此可在 UI 上做区分提示
                    "skipped_due_to_dock_card": True,
                },
            }

        # 如果是对接卡券，执行发货前校验（余额、价格覆盖等）
        if card_source in ('dock_l1', 'dock_l2') and dock_record_id:
            card_dict = {
                'id': request.card_id,
                'card_source': card_source,
                'dock_record_id': dock_record_id,
            }
            validate_ok = await xianyu_live.auto_delivery_handler._validate_dock_delivery(
                request.order_no, card_dict
            )
            if not validate_ok:
                # 获取具体的校验失败原因
                fail_reason = getattr(xianyu_live.auto_delivery_handler, '_last_delivery_fail_reason', '')
                logger.warning(f"【内部API】对接卡券发货校验未通过: order_no={request.order_no}, card_source={card_source}, 原因={fail_reason}")
                # 将失败原因写入订单表
                # card_only 模式：pre_check 已写入"禁止发货原因"（更精确），不要被对接校验失败原因覆盖
                if skip_confirm_for_card_only:
                    logger.info(
                        f"【内部API】card_only 模式且对接卡券校验失败：保留 pre_check 写入的禁止发货原因，"
                        f"不覆盖。order_no={request.order_no}"
                    )
                else:
                    try:
                        from common.db.session import async_session_maker
                        from common.services.order_service import OrderService
                        async with async_session_maker() as fail_session:
                            order_svc = OrderService(fail_session)
                            await order_svc.update_order_delivery_fail_reason(
                                request.order_no,
                                fail_reason or "对接卡券发货校验未通过"
                            )
                    except Exception as e:
                        logger.warning(f"记录发货失败原因到订单表失败: {e}")
                return {
                    "success": False,
                    "code": 400,
                    "message": fail_reason or "对接卡券发货校验未通过（余额不足或售价不覆盖成本+手续费）",
                    "data": None
                }
        
        # ============ 多数量发货支持 ============
        # 订单数量：>=1，控制循环次数，N 张卡券逐一获取并发送（与 auto_delivery_handler
        # multi_quantity_delivery 流程语义对齐）。任何卡券类型都先做基本校验再开始循环。
        quantity = max(1, int(request.quantity or 1))

        # card_only 多数量退化保护：订单已被关闭 + 仅补发卡券是商家"礼貌性安抚"语义，
        # 多数量场景下 N 倍补发会让货主多承担 N-1 张卡密成本（特别是 data/api 实际卡密会扣库存/调 API）。
        # card_only 流程下强制 quantity=1（业务上 card_only 就是补 1 张），调用方收到的 is_card_only=True
        # 已经隐含了"就 1 张"语义，不再单独加退化标记字段。
        if quantity > 1 and skip_confirm_for_card_only:
            logger.warning(
                f"【内部API】订单 {request.order_no} card_only 模式仅补发 1 张固定卡券，"
                f"已退化为 1 张（quantity={quantity} -> 1）"
            )
            quantity = 1

        # 商品级多数量发货开关：与 auto_delivery_handler 保持一致行为
        # 商家在商品配置里关闭多数量发货时，即使订单 quantity>1 也强制按单数量处理。
        # 这是商家主动配置的意愿（"宁可手动补发也不批量扣库存"），不写 fail_reason 打扰，
        # 仅在响应里带 quantity_degraded_for_disabled_switch 标记让调用方观测。
        quantity_degraded_for_disabled_switch = False
        if quantity > 1:
            try:
                multi_quantity_enabled = db_manager.get_item_multi_quantity_delivery_status(account_id, request.item_id)
            except Exception as switch_err:
                # 开关查询异常时按"未启用"处理（保守策略）
                logger.warning(f"【内部API】查询商品多数量发货开关异常，按未启用处理: {switch_err}")
                multi_quantity_enabled = False
            if not multi_quantity_enabled:
                logger.info(
                    f"【内部API】订单 {request.order_no} 商品 {request.item_id} 未开启多数量发货开关，"
                    f"按单数量处理（quantity={quantity} -> 1）"
                )
                quantity = 1
                quantity_degraded_for_disabled_switch = True

        # 对接卡券（dock_l1/dock_l2）多数量发货安全门：强制退化为 1 张
        # 原因：底层 _create_agent_order + settlement_service 是按"1 笔订单 1 笔代理订单"的语义实现，
        # 循环 N 次调用会触发以下已知金额 bug：
        #   1. 手续费按"卡密"重复扣 N 次（应按订单只扣 1 次）—— 资损货主
        #   2. _validate_dock_delivery 余额校验只算单张，循环到 2~N 张可能扣款失败但卡密已发出
        #   3. agent_order.sale_price 每笔都记订单总价 → 后台聚合销售额虚增 (N-1)/N 倍
        #   4. agent_order.profit 每笔都记 (总价 - 单价) → 利润字段失真
        # 短期防御：对接卡券的多数量订单退化为 1 张，并在响应里带 quantity_degraded_for_dock_card 标记，
        # 由调用方提示商家手动拆单或改用自有卡券；待财务结算逻辑改造后再放开。
        quantity_degraded_for_dock = False
        if quantity > 1 and card_source in ('dock_l1', 'dock_l2'):
            logger.warning(
                f"【内部API】订单 {request.order_no} 对接卡券暂不支持多数量发货，"
                f"已退化为 1 张（quantity={quantity} -> 1，card_source={card_source}）"
            )
            quantity = 1
            quantity_degraded_for_dock = True

        # text/image 固定内容卡券多数量发货安全门：强制退化为 1 张
        # 原因：text 类型每次返回相同 card.text_content，image 类型每次返回相同 card.image_url，
        # 循环 N 次只是把同一段话/同一张图重复发 N 次，业务上无意义且会打扰买家。
        # 商家若需要多数量真正发不同卡密，应改用 data（批量数据）或 api（接口拉取）类型卡券。
        quantity_degraded_for_fixed_content = False
        if quantity > 1 and card.type in ('text', 'image'):
            logger.warning(
                f"【内部API】订单 {request.order_no} 固定内容卡券（{card.type} 类型）不支持多数量发货，"
                f"已退化为 1 张（quantity={quantity} -> 1）"
            )
            quantity = 1
            quantity_degraded_for_fixed_content = True

        if quantity > 1:
            logger.info(f"【内部API】订单 {request.order_no} 多数量发货: quantity={quantity}, card_type={card.type}")

        # 不支持的卡券类型直接拒绝
        if card.type not in ('text', 'data', 'image', 'api'):
            logger.error(f"【内部API】不支持的卡券类型: {card.type}")
            return {
                "success": False,
                "code": 400,
                "message": f"不支持的卡券类型: {card.type}",
                "data": None
            }

        # image 类型预校验：必须有 image_url，否则直接失败
        if card.type == 'image' and not card.image_url:
            logger.error(f"【内部API】图片卡券缺少图片URL: card_id={request.card_id}")
            return {
                "success": False,
                "code": 400,
                "message": "图片卡券缺少图片URL",
                "data": None
            }

        # 构建订单上下文（仅 text/data/api 文字渲染需要）
        from app.services.xianyu.delivery_utils import process_delivery_content_with_description
        _order_context = {
            'order_id': request.order_no or '',
            'item_id': request.item_id or '',
            'item_title': '',
            'buyer_name': '',
            'buyer_id': request.buyer_id or '',
            'seller_name': '',
        }
        try:
            _item_info = db_manager.get_item_info(account_id, request.item_id)
            if _item_info:
                _order_context['item_title'] = _item_info.get('title') or ''
            _seller_info = db_manager.get_cookie_by_id(account_id)
            if _seller_info:
                _order_context['seller_name'] = _seller_info.get('remark') or account_id or ''
            # 买家明文昵称：复用自动发货同一套逻辑（pre_check 阶段已获取 _current_buyer_fish_nick，
            # 缺失则用 chat_id 实时查 mtop user.query），手动发货无推送昵称，兜底传空
            _order_context['buyer_name'] = await xianyu_live.auto_delivery_handler._resolve_buyer_name_for_variable(
                card.description or '', request.chat_id, ''
            )
        except Exception:
            pass

        # ============ 消费+发送一体化循环 ============
        # 关键设计：每一轮把"获取内容"和"发送"绑定为原子动作，无论发送成功/失败都把
        # 原始内容写入 final_contents（失败带[发送失败-请手动转发]标记），保证已扣库存的卡密
        # 都能通过订单 delivery_content 字段追溯（避免 data/api 类型扣了库存但买家没收到、
        # 订单也没记录的资损盲区）。
        # raw_contents     : 每张卡密的"原始内容"（用于对接卡券创建代理订单时的内容字段）
        # final_contents   : 每张卡密的"最终展示内容"（含失败标记），用于订单 delivery_content
        # failed_indices   : 发送失败的下标（1-based），用于响应暴露给调用方
        raw_contents: list[str] = []
        final_contents: list[str] = []
        failed_indices: list[int] = []
        early_break_reason: str | None = None  # 库存不足 / api 失败导致提前结束的原因

        for i in range(quantity):
            # ---- 1. 获取本张卡密的原始内容 ----
            content = None
            if card.type == 'text':
                content = card.text_content
            elif card.type == 'data':
                content = db_manager.consume_batch_data(request.card_id)
                if not content:
                    if not raw_contents:
                        logger.error(f"【内部API】批量数据已用完: card_id={request.card_id}")
                        return {
                            "success": False,
                            "code": 400,
                            "message": "批量数据已用完",
                            "data": None
                        }
                    early_break_reason = (
                        f"批量数据库存不足：第 {i+1}/{quantity} 张消费时已用完"
                    )
                    logger.warning(f"【内部API】{early_break_reason}")
                    break
            elif card.type == 'image':
                content = card.image_url
            elif card.type == 'api':
                rule = {
                    'card_id': card.id,
                    'card_name': card.name,
                    'card_type': card.type,
                    'card_api_config': card.api_config,
                    'card_description': card.description,
                }
                content = await xianyu_live.auto_delivery_handler._get_api_card_content(
                    rule=rule,
                    order_id=request.order_no,
                    item_id=request.item_id,
                    buyer_id=request.buyer_id,
                    chat_id=request.chat_id
                )
                if not content:
                    if not raw_contents:
                        logger.error(f"【内部API】API调用失败，未获取到发货内容")
                        return {
                            "success": False,
                            "code": 500,
                            "message": "API调用失败",
                            "data": None
                        }
                    early_break_reason = (
                        f"API 中途失败：第 {i+1}/{quantity} 张未获取到内容"
                    )
                    logger.warning(f"【内部API】{early_break_reason}")
                    break

            if not content:
                continue

            raw_contents.append(content)
            idx = len(raw_contents)  # 1-based 当前序号
            if quantity > 1:
                logger.info(f"【内部API】第 {idx}/{quantity} 张卡券内容已获取")

            # ---- 2. 立刻发送本张内容（成功/失败都记录到 final_contents） ----
            send_ok = False
            try:
                if card.type == 'image':
                    logger.info(
                        f"【内部API】发送图片消息 第 {idx}/{quantity}: {content}"
                        if quantity > 1 else f"【内部API】发送图片消息: {content}"
                    )
                    await xianyu_live.send_image_msg(
                        ws,
                        request.chat_id,
                        request.buyer_id,
                        content,
                        request.card_id
                    )
                    final_contents.append(f"[图片]{content}")
                    send_ok = True
                else:
                    rendered = process_delivery_content_with_description(
                        content,
                        card.description or '',
                        _order_context
                    )
                    logger.info(
                        f"【内部API】发送文本消息 第 {idx}/{quantity}: {rendered[:50]}..."
                        if quantity > 1 else f"【内部API】发送文本消息: {rendered[:50]}..."
                    )
                    await xianyu_live.auto_delivery_handler._send_text_with_separator(
                        ws,
                        request.chat_id,
                        request.buyer_id,
                        rendered
                    )
                    final_contents.append(rendered)
                    send_ok = True
            except Exception as send_err:
                # 发送失败时仍把"原始内容"写入 final_contents 但带失败标记，保证库存被消费的卡密
                # 都能在订单 delivery_content 中追溯，避免数据丢失。商家可从这里手动复制转发。
                failed_indices.append(idx)
                logger.error(f"【内部API】第 {idx}/{quantity} 张卡券发送异常: {send_err}")
                if card.type == 'image':
                    final_contents.append(f"[图片-发送失败-请手动转发]{content}")
                else:
                    # 失败的内容仍按原始 content 记录（不渲染备注，保留原始可复用形态）
                    final_contents.append(f"[发送失败-请手动转发] {content}")

            # ---- 3. 多张之间间隔 1 秒（即使发送失败也间隔，避免风控） ----
            if quantity > 1 and i < quantity - 1:
                await asyncio.sleep(1)

        # 没有获取到任何内容：双重保险（前面已 return，这里防御性兜底）
        if not raw_contents:
            logger.error(f"【内部API】未获取到任何发货内容: order_no={request.order_no}")
            return {
                "success": False,
                "code": 500,
                "message": "未获取到任何发货内容",
                "data": None
            }

        actual_count = len(raw_contents)
        send_failed_count = len(failed_indices)
        send_success_count = actual_count - send_failed_count

        # ============ "卡券发送成功再确认发货"模式：卡券已发送，现在执行确认发货 ============
        send_before_confirm_fail_msg: str | None = None
        if send_before_confirm_mode and send_success_count > 0 and send_failed_count == 0:
            logger.info(f"【内部API】卡券全部发送成功，开始执行确认发货: order_no={request.order_no}")
            if xianyu_live.is_auto_confirm_enabled():
                # 先执行免拼（如果是小刀订单）
                if request.is_bargain:
                    logger.info(f"【内部API】send_before_confirm 模式：卡券发送后调用免拼接口: order_no={request.order_no}")
                    freeshipping_result = await xianyu_live.auto_delivery_handler.auto_freeshipping(
                        order_id=request.order_no,
                        item_id=request.item_id,
                        buyer_id=request.buyer_id
                    )
                    if freeshipping_result and freeshipping_result.get('success'):
                        logger.info(f"【内部API】卡券发送后免拼发货成功: order_no={request.order_no}")
                    else:
                        fs_error = freeshipping_result.get('error', '未知错误') if freeshipping_result else '未知错误'
                        logger.warning(f"【内部API】卡券发送后免拼发货失败: {fs_error}，order_no={request.order_no}")

                confirm_result = await xianyu_live.auto_delivery_handler.auto_confirm(
                    order_id=request.order_no,
                    item_id=request.item_id
                )
                if confirm_result and confirm_result.get('success'):
                    logger.info(f"【内部API】🎉 卡券发送后确认发货成功: order_no={request.order_no}")
                else:
                    confirm_error = confirm_result.get('error', '未知错误') if confirm_result else '未知错误'
                    send_before_confirm_fail_msg = f"⚠️ 卡券已发送成功，但确认发货失败: {confirm_error}，请手动确认发货"
                    logger.warning(f"【内部API】{send_before_confirm_fail_msg}，order_no={request.order_no}")
            else:
                send_before_confirm_fail_msg = "⚠️ 卡券已发送成功，但自动确认发货已关闭，请手动确认发货"
                logger.info(f"【内部API】自动确认发货已关闭，卡券已发送但跳过确认发货: order_no={request.order_no}")
        elif send_before_confirm_mode and send_failed_count > 0:
            send_before_confirm_fail_msg = f"⚠️ 卡券发送存在失败（{send_failed_count}张），已跳过确认发货，请检查买家是否收到完整内容后手动确认发货"
            logger.warning(f"【内部API】卡券发送存在失败（{send_failed_count}张），跳过确认发货: order_no={request.order_no}")

        # ============ 累计发货次数（按实际发出的张数） ============
        for _ in range(actual_count):
            try:
                db_manager.increment_delivery_count(request.card_id)
            except Exception as cnt_err:
                logger.warning(f"【内部API】累加卡券发货次数失败: {cnt_err}")

        # ============ 合并 content 写入订单状态（一次性 commit） ============
        combined_content = "\n---\n".join(final_contents) if actual_count > 1 else (final_contents[0] if final_contents else '')

        # 部分异常场景的 fail_reason 提示文案（库存不足 / api 中途失败 / 发送失败）
        # 必须在 update_order_delivery_info 之后写入，否则会被其内部的 delivery_fail_reason=None 清空。
        # card_only 模式走 record_delivery_for_closed_order 不清空 fail_reason，可省略追加。
        requested_quantity = int(request.quantity or 1)
        partial_warn_msg: str | None = None
        # 退化场景的 fail_reason 处理策略：
        # - dock / fixed_content：由调用方（redelivery_task / orders.py）写入退化提示文案
        # - disabled_switch：商家主动配置不发多数量，不写 fail_reason 不打扰商家
        # - card_only：订单已被关闭，pre_check 已写入"禁止发货原因"，本处不应覆盖也不应追加
        # internal API 这里只处理"非退化的部分异常"，避免重复写入或意外打扰。
        if (
            not quantity_degraded_for_dock
            and not quantity_degraded_for_fixed_content
            and not quantity_degraded_for_disabled_switch
            and not skip_confirm_for_card_only
        ):
            warn_parts: list[str] = []
            if actual_count < requested_quantity:
                # 库存不足或 api 中途失败导致少发
                missing = requested_quantity - actual_count
                if early_break_reason:
                    warn_parts.append(f"⚠️ 仅发出 {actual_count}/{requested_quantity} 张：{early_break_reason}，剩余 {missing} 张请补充库存或手动补发")
                else:
                    warn_parts.append(f"⚠️ 仅发出 {actual_count}/{requested_quantity} 张，剩余 {missing} 张请手动补发")
            if send_failed_count > 0:
                warn_parts.append(
                    f"⚠️ 共 {send_failed_count} 张消息发送失败（第 {','.join(map(str, failed_indices))} 张），"
                    f"请在订单内容中复制[发送失败-请手动转发]开头的卡密手动补发给买家"
                )
            if warn_parts:
                partial_warn_msg = "；".join(warn_parts)

        try:
            from common.services.order_service import OrderService
            async with async_session_maker() as db_session:
                order_service = OrderService(db_session)
                if skip_confirm_for_card_only:
                    await order_service.record_delivery_for_closed_order(
                        order_no=request.order_no,
                        delivery_method=request.delivery_method,
                        delivery_content=combined_content,
                        buyer_fish_nick=xianyu_live.auto_delivery_handler._current_buyer_fish_nick,
                    )
                    logger.info(
                        f"【内部API】订单 {request.order_no} card_only 模式：已记录补发卡券内容（订单状态保持已关闭，共 {actual_count} 张）"
                    )
                else:
                    await order_service.update_order_delivery_info(
                        order_no=request.order_no,
                        status="shipped",
                        delivery_method=request.delivery_method,
                        delivery_content=combined_content,
                        buyer_fish_nick=xianyu_live.auto_delivery_handler._current_buyer_fish_nick,
                    )
                    logger.info(
                        f"【内部API】订单 {request.order_no} 状态已更新为已发货（共 {actual_count} 张）"
                    )
                # 在状态更新之后写 fail_reason 提示（避免被 update_order_delivery_info 内部清空）
                # 合并所有需要写入的 fail_reason（partial_warn_msg + send_before_confirm_fail_msg）
                combined_fail_reasons = []
                if partial_warn_msg:
                    combined_fail_reasons.append(partial_warn_msg)
                if send_before_confirm_fail_msg:
                    combined_fail_reasons.append(send_before_confirm_fail_msg)
                if combined_fail_reasons:
                    final_fail_reason = "；".join(combined_fail_reasons)
                    await order_service.update_order_delivery_fail_reason(
                        request.order_no, final_fail_reason
                    )
                    logger.warning(
                        f"【内部API】订单 {request.order_no} 失败原因已写入: {final_fail_reason}"
                    )
        except Exception as e:
            logger.error(f"【内部API】更新订单状态失败: {e}")

        # ============ 对接卡券：按实际发出的张数创建 N 笔代理订单 ============
        # 每张卡密都意味着货主侧实际报废 1 张包货成本，必须按张创建独立的代理订单，
        # 由 _create_agent_order 内部按单价逐笔扣货主余额并分润给上下级，
        # 与"按数量倒 N 笔"的财务结算策略一致（避免 N 倍金额单笔订单引起退款核对失真）。
        if card_source in ('dock_l1', 'dock_l2') and dock_record_id:
            card_dict = {
                'id': request.card_id,
                'card_source': card_source,
                'dock_record_id': dock_record_id,
            }
            for i in range(actual_count):
                try:
                    await xianyu_live.auto_delivery_handler._create_agent_order(
                        order_id=request.order_no,
                        item_id=request.item_id,
                        card=card_dict,
                        delivery_content=raw_contents[i] if i < len(raw_contents) else '',
                        buyer_id=request.buyer_id,
                    )
                except Exception as agent_err:
                    logger.error(
                        f"【内部API】创建代理订单失败 第 {i+1}/{actual_count}（不影响发货）: {agent_err}"
                    )

        # ============ 返回响应 ============
        if quantity_degraded_for_dock:
            # 对接卡券退化提示：商家需要明确知道本次只发了 1 张
            success_msg = (
                f"对接卡券暂不支持多数量发货，已发送 1 张（订单数量为 {request.quantity} 张）。"
                f"请手动补发剩余卡密，或拆分订单/改用自有卡券"
            )
        elif quantity_degraded_for_fixed_content:
            # text/image 固定内容卡券退化提示：建议商家改用 data/api 类型
            success_msg = (
                f"固定内容卡券（{card.type} 类型）不支持多数量发货，已发送 1 张固定内容"
                f"（订单数量为 {request.quantity} 张）。如需多数量发送不同卡密，请改用 data 或 api 类型卡券"
            )
        elif card.type == 'image':
            success_msg = (
                f"图片发货成功（共 {actual_count} 张）"
                if not skip_confirm_for_card_only
                else f"card_only 模式：仅补发图片卡券（共 {actual_count} 张），订单已被关闭"
            )
        else:
            success_msg = (
                f"发货成功（共 {actual_count} 张）"
                if not skip_confirm_for_card_only
                else f"card_only 模式：仅补发卡券内容（共 {actual_count} 张），订单已被关闭"
            )

        # 在 success_msg 末尾追加部分异常说明（库存不足 / 发送失败），让前端调用方一眼看到
        if partial_warn_msg:
            success_msg = f"{success_msg}（{partial_warn_msg}）"

        response_data = {
            "order_no": request.order_no,
            "delivery_type": card.type,
            "content": combined_content,
            "delivery_method": request.delivery_method,
            # is_card_only=True 告知调用方：订单已被关闭，调用方不要再把本地状态改为 'shipped'
            "is_card_only": skip_confirm_for_card_only,
            # 多数量发货：本次实际成功发出的张数（可能 < quantity，例如 data/api 中途耗尽）
            "quantity_requested": requested_quantity,
            "quantity_sent": actual_count,
            # 对接卡券多数量退化标记：True 表示原本订单 quantity>1 但因对接卡券强制退化为 1 张,
            # 调用方应据此向商家提示：手动补发剩余/拆单/改用自有卡券。
            "quantity_degraded_for_dock_card": quantity_degraded_for_dock,
            # text/image 固定内容卡券多数量退化标记：True 表示原本订单 quantity>1 但因卡券类型固定退化为 1 张,
            # 调用方应据此向商家提示：改用 data/api 类型卡券支持多数量。
            "quantity_degraded_for_fixed_content": quantity_degraded_for_fixed_content,
            # 商品级多数量发货开关关闭导致退化：商家主动配置，调用方不应写 fail_reason 打扰商家
            "quantity_degraded_for_disabled_switch": quantity_degraded_for_disabled_switch,
            # 发送失败信息：失败张数和失败下标（1-based），让调用方/商家明确知道哪些张需要手动补发
            # 失败的卡密原始内容已带"[发送失败-请手动转发]"标记追加在订单 delivery_content 中，
            # 商家可从订单详情复制后手动转发给买家
            "send_failed_count": send_failed_count,
            "send_failed_indices": failed_indices,
            # 提前结束原因（库存不足 / api 中途失败），None 表示循环走完未提前结束
            "early_break_reason": early_break_reason,
        }
        if card.type == 'image':
            # 兼容旧字段：单张图片场景仍返回 image_url
            response_data["image_url"] = raw_contents[0] if raw_contents else card.image_url

        return {
            "success": True,
            "code": 200,
            "message": success_msg,
            "data": response_data
        }
        
    except Exception as e:
        logger.error(f"【内部API】订单发货异常: {str(e)}", exc_info=True)
        return {
            "success": False,
            "code": 500,
            "message": f"订单发货异常: {str(e)}",
            "data": None,
        }



@router.post("/accounts/{account_id}/refresh-token")
async def refresh_token(account_id: str):
    """
    刷新账号Token
    
    Args:
        account_id: 账号ID
        
    Returns:
        刷新结果
    """
    from loguru import logger
    from app.services.xianyu.xianyu_async import XianyuAsync
    
    logger.info(f"【内部API】收到Token刷新请求: account_id={account_id}")
    
    # 获取 XianyuAsync 实例
    instance = XianyuAsync.get_instance(account_id)
    
    if not instance:
        raise HTTPException(
            status_code=404,
            detail=f"账号 {account_id} 未启动或不存在"
        )
    
    # 触发 Token 刷新
    try:
        if instance.token_manager:
            # 使用 token_manager 触发刷新
            await instance.token_manager.trigger_refresh()
            logger.info(f"【内部API】Token刷新请求已提交: account_id={account_id}")
            
            return {
                "success": True,
                "code": 200,
                "message": "Token刷新请求已提交",
                "data": {
                    "account_id": account_id
                }
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Token管理器未初始化"
            )
    except Exception as e:
        logger.error(f"【内部API】Token刷新失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Token刷新失败: {str(e)}"
        )


class PasswordLoginRefreshRequest(BaseModel):
    """密码登录刷新请求"""
    trigger_reason: str = "账号已掉线"  # 触发原因


@router.post("/accounts/{account_id}/password-login-refresh")
async def password_login_refresh(account_id: str, request: PasswordLoginRefreshRequest = None):
    """
    触发账号密码登录刷新Cookie（异步，立即返回）
    
    当检测到Session过期时，定时任务可以调用此接口触发密码登录刷新Cookie。
    此接口会在后台启动密码登录任务，立即返回，不等待登录完成。
    
    Args:
        account_id: 账号ID
        request: 请求参数（可选）
        
    Returns:
        操作结果（任务已启动）
    """
    import asyncio
    from loguru import logger
    from app.services.captcha.password_login_state import password_login_state
    
    trigger_reason = request.trigger_reason if request else "账号已掉线"
    logger.info(f"【内部API】收到密码登录刷新请求: account_id={account_id}, 原因={trigger_reason}")
    
    # 检查账号是否正在处理中，防止重复触发
    if not password_login_state.start_processing(account_id):
        # 账号正在处理中，直接返回成功（丢弃请求，不报错）
        logger.info(f"【内部API】账号 {account_id} 正在处理密码登录，丢弃本次请求")
        return {
            "success": True,
            "code": 200,
            "message": "账号正在处理中，本次请求已丢弃",
            "data": {"account_id": account_id, "status": "already_processing"}
        }
    
    # 在后台启动密码登录任务，不等待结果
    asyncio.create_task(_execute_password_login_refresh(account_id, trigger_reason))
    
    logger.info(f"【内部API】密码登录任务已启动: account_id={account_id}")
    return {
        "success": True,
        "code": 200,
        "message": "密码登录任务已启动",
        "data": {"account_id": account_id, "status": "started"}
    }


async def _execute_password_login_refresh(account_id: str, trigger_reason: str):
    """
    后台执行密码登录刷新（异步任务）
    
    Args:
        account_id: 账号ID
        trigger_reason: 触发原因
    """
    from loguru import logger
    from app.services.xianyu.cookie_manager import get_manager
    from app.services.captcha.password_login_state import password_login_state
    
    try:
        # 获取 CookieManager 实例
        manager = get_manager()
        xianyu_live = manager.instances.get(account_id)
        
        if not xianyu_live:
            # 实例不存在，尝试直接执行密码登录（不依赖运行中的实例）
            logger.warning(f"【内部API】账号 {account_id} 实例未运行，尝试独立执行密码登录")
            await _standalone_password_login(account_id, trigger_reason)
            return
        
        # 调用 cookie_token_manager 的密码登录刷新方法
        if hasattr(xianyu_live, 'cookie_token_manager') and xianyu_live.cookie_token_manager:
            refresh_result = await xianyu_live.cookie_token_manager.try_password_login_refresh(trigger_reason)
            
            if refresh_result == "no_credentials":
                logger.warning(f"【内部API】账号 {account_id} 未配置用户名或密码")
            elif refresh_result == True:
                logger.info(f"【内部API】账号 {account_id} 密码登录刷新成功")
            else:
                logger.warning(f"【内部API】账号 {account_id} 密码登录刷新失败")
        else:
            # CookieTokenManager 未初始化，回退到独立执行密码登录
            logger.warning(f"【内部API】账号 {account_id} 的 CookieTokenManager 未初始化，尝试独立执行密码登录")
            await _standalone_password_login(account_id, trigger_reason)
            
    except Exception as e:
        logger.error(f"【内部API】密码登录刷新异常: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # 清理密码登录处理状态
        password_login_state.finish_processing(account_id)


async def _standalone_password_login(account_id: str, trigger_reason: str) -> dict:
    """
    独立执行密码登录（不依赖运行中的实例）
    
    当 WebSocket 实例未运行时，直接从数据库获取账号信息并执行密码登录。
    
    Args:
        account_id: 账号ID
        trigger_reason: 触发原因
        
    Returns:
        操作结果字典
    """
    import asyncio
    import time as _time
    from loguru import logger
    from common.db.compat import db_manager
    
    logger.info(f"【内部API】开始独立执行密码登录: account_id={account_id}")
    
    # 记录账号登录日志的辅助函数
    start_ts = _time.time()
    login_username: str | None = None
    # 接口续期失败原因（在接口续期失败后赋值，供后续日志拼接）
    _api_renew_fail_msg: str = ""

    def _record_login_log(
        login_status: str,
        failure_reason: str | None = None,
        error_message: str | None = None,
        updated_cookie_names: str | None = None,
    ) -> None:
        """记录一条账号登录日志（写日志失败不影响主流程）。"""
        try:
            duration_ms = int((_time.time() - start_ts) * 1000)
            # 如果接口续期失败了，在 error_message 前拼接续期失败信息
            final_error_message = error_message
            if _api_renew_fail_msg and error_message:
                final_error_message = f"{_api_renew_fail_msg}，{error_message}"
            db_manager.add_account_login_log(
                cookie_id=account_id,
                login_status=login_status,
                username=login_username,
                trigger_reason=trigger_reason,
                failure_reason=failure_reason,
                error_message=final_error_message,
                updated_cookie_names=updated_cookie_names,
                duration_ms=duration_ms,
            )
        except Exception as log_e:
            logger.warning(f"【内部API】写入账号登录日志失败: {log_e}")

    try:
        # 从数据库获取账号信息
        account_info = await asyncio.to_thread(db_manager.get_cookie_details, account_id)
        
        if not account_info:
            logger.error(f"【内部API】无法获取账号信息: {account_id}")
            _record_login_log("failed", "account_info_missing", "账号不存在")
            return {
                "success": False,
                "code": 404,
                "message": "账号不存在",
                "data": {"account_id": account_id}
            }
        
        login_username = (account_info.get('username') or '') or None

        # ====== 优先尝试接口续期（轻量级，无需浏览器和密码） ======
        cookies_str = account_info.get('cookie_value', '')
        if cookies_str and cookies_str.strip():
            try:
                from common.services.cookie_renew_api_service import cookie_renew_api_service
                logger.info(f"【内部API】账号 {account_id} 先尝试接口续期...")
                # 记录续期前的全量cookies
                logger.info(f"【{account_id}】[续期前全量Cookies] {cookies_str}")
                renew_result = await cookie_renew_api_service.renew(cookies_str, account_id)

                # 不管续期是否成功，有Cookie更新就先写库
                if renew_result.updated_cookie_names:
                    db_manager.update_cookie_account_info(
                        account_id,
                        cookie_value=renew_result.new_cookies_str
                    )
                    logger.info(
                        f"【内部API】账号 {account_id} 接口返回Cookie已更新 "
                        f"{len(renew_result.updated_cookie_names)} 个字段"
                    )

                # 记录续期后的全量cookies（不管成功失败都打印）
                logger.info(f"【{account_id}】[续期后全量Cookies] {renew_result.new_cookies_str or cookies_str}")

                if renew_result.success:
                    renew_method_desc = "接口续期" if renew_result.renew_method == "api" else "浏览器续期"
                    logger.info(f"【内部API】账号 {account_id} {renew_method_desc}成功，跳过密码登录")
                    log_reason = "api_renew_success" if renew_result.renew_method == "api" else "browser_renew_success"
                    _record_login_log(
                        "success",
                        log_reason,
                        f"{renew_method_desc}成功，更新了 {len(renew_result.updated_cookie_names)} 个字段，无需密码登录",
                        updated_cookie_names=",".join(renew_result.updated_cookie_names) if renew_result.updated_cookie_names else None,
                    )
                    return {
                        "success": True,
                        "code": 200,
                        "message": f"{renew_method_desc}成功，更新了 {len(renew_result.updated_cookie_names)} 个字段，无需密码登录",
                        "data": {"account_id": account_id, "method": log_reason}
                    }
                else:
                    logger.info(
                        f"【内部API】账号 {account_id} 续期未成功"
                        f"（{renew_result.api_message}），继续尝试密码登录..."
                    )
            except Exception as renew_exc:
                logger.warning(f"【内部API】账号 {account_id} 续期异常（不影响密码登录）: {renew_exc}")

        # ====== 续期未成功，继续密码登录流程 ======
        _api_renew_fail_msg = "接口续期和浏览器续期均失败"
        username = account_info.get('username', '')
        password = account_info.get('password', '')
        show_browser = account_info.get('show_browser', False)
        
        if not username or not password:
            err_msg = f"{_api_renew_fail_msg}，且未配置用户名或密码，账号已自动禁用"
            logger.warning(f"【内部API】账号 {account_id} 未配置用户名或密码")
            # 自动禁用账号
            try:
                db_manager.disable_account(account_id, reason=f"{trigger_reason}且未配置密码，自动禁用")
                logger.warning(f"【内部API】账号 {account_id} 已自动禁用")
            except Exception as disable_e:
                logger.error(f"【内部API】自动禁用账号失败: {disable_e}")
            
            _record_login_log("no_credentials", "no_credentials", err_msg)
            return {
                "success": False,
                "code": 400,
                "message": "未配置用户名或密码，账号已自动禁用",
                "data": {"account_id": account_id, "reason": "no_credentials"}
            }
        
        # 使用 Playwright 执行密码登录
        from app.services.captcha.xianyu_slider_stealth import XianyuSliderStealth
        
        browser_mode = "有头" if show_browser else "无头"
        logger.info(f"【内部API】使用{browser_mode}浏览器进行密码登录: {username}")
        
        def _do_login():
            slider = XianyuSliderStealth(
                user_id=account_id,
                enable_learning=False,
                headless=not show_browser
            )
            try:
                return slider.login_with_password_playwright(
                    account=username,
                    password=password,
                    show_browser=show_browser
                )
            finally:
                try:
                    slider.close()
                except Exception:
                    pass
        
        result = await asyncio.to_thread(_do_login)
        
        if result:
            # 登录成功，更新数据库中的Cookie
            new_cookies_str = '; '.join([f"{k}={v}" for k, v in result.items()])
            # 记录密码登录获取到的新cookies
            logger.info(f"【{account_id}】[密码登录获取的新Cookies] {new_cookies_str}")
            
            success = db_manager.update_cookie_account_info(
                account_id,
                cookie_value=new_cookies_str
            )
            
            if success:
                logger.info(f"【内部API】账号 {account_id} 密码登录成功，Cookie已更新到数据库")
                
                # 清除Token缓存
                try:
                    from common.db.session import async_session_maker
                    from sqlalchemy import text
                    unb = result.get('unb', '')
                    if unb:
                        async with async_session_maker() as session:
                            await session.execute(
                                text("DELETE FROM xy_token_cache WHERE user_id = :user_id"),
                                {"user_id": unb}
                            )
                            await session.commit()
                            logger.info(f"【内部API】已清除Token缓存: user_id={unb}")
                except Exception as cache_e:
                    logger.warning(f"【内部API】清除Token缓存失败: {cache_e}")
                
                _record_login_log("success", None, "密码登录成功，Cookie已更新")
                return {
                    "success": True,
                    "code": 200,
                    "message": "密码登录成功，Cookie已更新",
                    "data": {"account_id": account_id, "cookie_count": len(result)}
                }
            else:
                logger.error(f"【内部API】账号 {account_id} 登录成功但更新数据库失败")
                _record_login_log("failed", "cookie_update_failed", "密码登录成功但更新数据库失败")
                return {
                    "success": False,
                    "code": 500,
                    "message": "登录成功但更新数据库失败",
                    "data": {"account_id": account_id}
                }
        else:
            logger.warning(f"【内部API】账号 {account_id} 密码登录失败")
            _record_login_log("failed", "login_no_cookie_returned", "密码登录失败，未获取到Cookie")
            return {
                "success": False,
                "code": 500,
                "message": "密码登录失败，未获取到Cookie",
                "data": {"account_id": account_id}
            }
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"【内部API】独立密码登录异常: {error_msg}")
        
        # ============== baxia-punish 风控图形滑块特殊处理 ==============
        try:
            from common.services.captcha.xianyu_slider_stealth import BaxiaPunishCaptchaException
            _is_baxia_punish = isinstance(e, BaxiaPunishCaptchaException)
        except Exception:
            _is_baxia_punish = False
        
        if _is_baxia_punish:
            logger.warning(
                f"【内部API】账号 {account_id} 触发风控图形滑块验证，账号本身正常，"
                f"仅设置 5 小时冷却（不禁用账号）：{error_msg}"
            )
            try:
                from common.utils.cookie_refresh import _password_error_cooldown
                import time as _time2
                _password_error_cooldown[account_id] = _time2.time()
            except Exception as cooldown_e:
                logger.warning(f"【内部API】写入风控冷却失败: {cooldown_e}")
            _record_login_log("failed", "baxia_punish_captcha", error_msg)
            return {
                "success": False,
                "code": 429,
                "message": (
                    f"触发闲鱼风控图形验证（如\"找两个松鼠\"），账号正常但暂时无法自动登录，"
                    f"已暂停 5 小时。请稍后重试或手动登录。"
                ),
                "data": {
                    "account_id": account_id,
                    "reason": "baxia_punish_captcha",
                    "cooldown_hours": 5,
                }
            }
        # ============== baxia-punish 处理结束 ==============
        
        # 检测账密错误，禁用账号
        is_bad_credentials = (
            '账密错误' in error_msg
            or '账号密码错误' in error_msg
            or '用户名或密码错误' in error_msg
        )
        if is_bad_credentials:
            disable_reason = error_msg if error_msg else "账号密码错误"
            try:
                db_manager.disable_account(account_id, reason=disable_reason)
                logger.warning(f"【内部API】检测到账密错误，账号 {account_id} 已自动禁用，原因: {disable_reason}")
            except Exception as disable_e:
                logger.error(f"【内部API】禁用账号失败: {disable_e}")
        
        _record_login_log(
            "failed",
            "bad_credentials" if is_bad_credentials else "exception",
            error_msg,
        )
        return {
            "success": False,
            "code": 500,
            "message": f"密码登录异常: {error_msg}",
            "data": {"account_id": account_id}
        }


@router.post("/accounts/{account_id}/create-chat")
async def create_chat(account_id: str, request: CreateChatRequest):
    """
    创建（或获取）单聊会话接口
    
    通过账号的活跃 WebSocket 连接向闲鱼发送 LWP 消息，
    等待服务端响应并返回会话ID（chat_id）。
    
    服务端按 (pairFirst, pairSecond, bizType) 幂等生成 cid，
    已存在的会话会直接返回现有 cid，不会重复创建。
    
    场景：订单手动发货时，如果订单缺少 chat_id，需要先创建会话再发货。
    
    Args:
        account_id: 账号ID
        request: 请求参数（买家ID、商品ID）
    
    Returns:
        操作结果，data.chat_id 为会话ID
    """
    try:
        from app.services.xianyu.cookie_manager import get_manager
        from loguru import logger
        
        logger.info(
            f"【内部API】收到创建会话请求: account_id={account_id}, "
            f"buyer_id={request.buyer_id}, item_id={request.item_id}"
        )
        
        if not request.buyer_id:
            return {
                "success": False,
                "code": 400,
                "message": "买家ID不能为空",
                "data": None
            }
        if not request.item_id:
            return {
                "success": False,
                "code": 400,
                "message": "商品ID不能为空",
                "data": None
            }
        
        # 获取 XianyuAsync 实例
        manager = get_manager()
        xianyu_live = manager.instances.get(account_id)
        
        if not xianyu_live:
            return {
                "success": False,
                "code": 404,
                "message": f"账号 {account_id} 未启动或不存在，请先启动账号",
                "data": None
            }
        
        # 检查 WebSocket 连接状态
        ws = xianyu_live.connection_manager.ws if xianyu_live.connection_manager else None
        if ws is None:
            return {
                "success": False,
                "code": 503,
                "message": f"账号 {account_id} 的 WebSocket 未连接，请等待连接建立或重启账号",
                "data": None
            }
        
        # 调用创建会话
        try:
            chat_id = await xianyu_live.create_chat_conversation(
                to_user_id=request.buyer_id,
                item_id=request.item_id,
            )
        except ConnectionError as ce:
            return {
                "success": False,
                "code": 503,
                "message": str(ce),
                "data": None
            }
        except TimeoutError as te:
            return {
                "success": False,
                "code": 504,
                "message": str(te),
                "data": None
            }
        except ValueError as ve:
            return {
                "success": False,
                "code": 500,
                "message": f"创建会话响应异常: {ve}",
                "data": None
            }
        
        logger.info(
            f"【内部API】创建会话成功: account_id={account_id}, "
            f"buyer_id={request.buyer_id}, chat_id={chat_id}"
        )
        return {
            "success": True,
            "code": 200,
            "message": "创建会话成功",
            "data": {
                "account_id": account_id,
                "buyer_id": request.buyer_id,
                "item_id": request.item_id,
                "chat_id": chat_id,
            }
        }
    except Exception as e:
        from loguru import logger
        import traceback
        logger.error(f"【内部API】创建会话异常: {e}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "code": 500,
            "message": f"创建会话异常: {str(e)}",
            "data": None
        }
