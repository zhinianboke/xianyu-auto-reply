from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from loguru import logger

from app.api import deps
from common.models.user import User
from common.schemas.common import ApiResponse
from common.schemas.order import OrderOut
from common.utils.auth_scope import resolve_owner_scope
from app.services.account_service import AccountService
from app.services.order_service import OrderService
from app.services.card_service import CardService
from app.services.websocket_client import websocket_client
from common.services.order_service import OrderDetailService
from common.models.xy_account import XYAccount
from sqlalchemy import select as order_select

from common.utils.time_utils import safe_isoformat
router = APIRouter(tags=["orders"])


class ManualDeliveryRequest(BaseModel):
    """手动发货请求"""
    order_no: str  # 订单号


class NoLogisticsDeliveryRequest(BaseModel):
    order_no: str


class CancelOrderRequest(BaseModel):
    order_no: str


class FetchXianyuOrdersRequest(BaseModel):
    """获取闲鱼订单请求"""
    cookie_id: str | None = None


class BatchDeleteOrdersRequest(BaseModel):
    """批量删除订单请求"""
    ids: list[int]


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "0.00"
    return format(value, "f")


@router.get("")
async def list_orders(
    cookie_id: str | None = Query(default=None, alias="cookie_id"),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, description="搜索关键词（订单号、商品ID、买家ID）"),
    delivery_method: str | None = Query(default=None, description="发货方式筛选：manual/auto/scheduled/none"),
    is_bargain: bool | None = Query(default=None, description="是否小刀筛选"),
    is_rated: bool | None = Query(default=None, description="是否已评价筛选"),
    start_date: str | None = Query(default=None, description="开始日期，格式：YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期，格式：YYYY-MM-DD"),
    delivery_send_status: str | None = Query(default=None, description="关联消息日志发送状态筛选：success/failed/unknown"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    order_service: OrderService = Depends(deps.get_order_service),
):
    """获取订单列表，支持多条件筛选
    
    管理员可查看所有订单。
    
    筛选条件：
    - delivery_method: 发货方式（manual=手动发货, auto=自动发货, scheduled=定时发货, none=未发货）
    - is_bargain: 是否小刀（true/false）
    - is_rated: 是否已评价（true/false）
    - start_date: 开始日期（YYYY-MM-DD）
    - end_date: 结束日期（YYYY-MM-DD）
    """
    owner_id, is_admin = resolve_owner_scope(current_user)

    if cookie_id and not is_admin:
        account = await account_service.get_account_for_user(current_user.id, cookie_id)
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    # 管理员查看所有订单，普通用户只看自己的
    orders, total, item_titles = await order_service.list_orders(
        owner_id,
        account_id=cookie_id,
        status=status_filter,
        search=search,
        delivery_method=delivery_method,
        is_bargain=is_bargain,
        is_rated=is_rated,
        start_date=start_date,
        end_date=end_date,
        delivery_send_status=delivery_send_status,
        page=page,
        page_size=page_size,
    )

    # 批量查询哪些订单是代销订单
    from sqlalchemy import select as sa_select
    from common.models.agent_order import AgentOrder
    order_nos = [o.order_no for o in orders if o.order_no]
    agent_order_nos: set[str] = set()
    if order_nos:
        from sqlalchemy import func as sa_func
        agent_stmt = sa_select(AgentOrder.order_no).where(AgentOrder.order_no.in_(order_nos))
        agent_result = await order_service.session.execute(agent_stmt)
        agent_order_nos = {row[0] for row in agent_result.all()}

    # 关联自动发货消息日志，取每个订单最新发送状态与失败原因
    delivery_log_map = await order_service.get_delivery_log_status_map(order_nos)

    payload = []
    for order in orders:
        spec_parts = [part for part in [order.spec_name, order.spec_value] if part]
        sku_info = " / ".join(spec_parts) if spec_parts else None
        # 从关联查询结果获取商品标题
        item_title = item_titles.get(order.item_id, "") if order.item_id else ""
        delivery_log = delivery_log_map.get(order.order_no) if order.order_no else None
        payload.append(
            OrderOut(
                id=str(order.id),
                order_id=order.order_no,
                cookie_id=order.account_id or "",
                item_id=order.item_id or "",
                item_title=item_title,
                buyer_id=order.buyer_id or "",
                buyer_fish_nick=order.buyer_fish_nick or "",
                chat_id=order.chat_id or "",
                sku_info=sku_info,
                quantity=order.quantity or 0,
                amount=_format_decimal(order.amount),
                status=(order.status or "unknown").lower(),
                is_bargain=order.is_bargain or False,
                is_rated=order.is_rated or False,
                is_red_flower=order.is_red_flower or False,
                receiver_name=order.receiver_name or "",
                receiver_phone=order.receiver_phone or "",
                receiver_address=order.receiver_address or "",
                delivery_method=order.delivery_method or "",
                delivery_content=order.delivery_content or "",
                delivery_fail_reason=order.delivery_fail_reason or "",
                delivery_send_status=(delivery_log or {}).get("send_status"),
                delivery_send_fail_reason=(delivery_log or {}).get("send_fail_reason"),
                is_agent_order=order.order_no in agent_order_nos,
                source=order.source or "",
                placed_at=order.placed_at,
                created_at=order.created_at,
                updated_at=order.updated_at,
            )
        )

    return {
        "success": True,
        "data": payload,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.post("/fetch-xianyu")
async def fetch_xianyu_orders(
    request: FetchXianyuOrdersRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    order_service: OrderService = Depends(deps.get_order_service),
):
    """获取闲鱼卖家订单并同步到数据库"""
    owner_id, _ = resolve_owner_scope(current_user)

    if request.cookie_id:
        account = await account_service.get_account_for_user(owner_id, request.cookie_id)
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
        accounts = [account]
    else:
        accounts = await account_service.list_accounts(owner_id)
        inactive_statuses = {"inactive", "disabled", "suspended", "deleted"}
        accounts = [acc for acc in accounts if (acc.status or "active") not in inactive_statuses]

    if not accounts:
        return {
            "success": True,
            "message": "没有可同步的账号",
            "data": {
                "total_fetched": 0,
                "new_inserted": 0,
                "updated": 0,
                "failed": 0,
                "accounts_processed": 0,
                "errors": [],
            },
        }

    total_fetched = 0
    new_inserted = 0
    updated = 0
    failed = 0
    errors: list[str] = []

    for account in accounts:
        try:
            logger.info(f"开始同步闲鱼订单: account_id={account.account_id}")
            result = await order_service.fetch_xianyu_orders(account)
            total_fetched += result.get("total_fetched", 0)
            new_inserted += result.get("new_inserted", 0)
            updated += result.get("updated", 0)
            failed += result.get("failed", 0)
            for error in result.get("errors", []):
                errors.append(f"{account.account_id}: {error}")
        except Exception as e:
            logger.error(f"同步闲鱼订单失败: account_id={account.account_id}, error={e}")
            errors.append(f"{account.account_id}: {str(e)}")

    return {
        "success": True,
        "message": f"同步完成，共处理 {len(accounts)} 个账号",
        "data": {
            "total_fetched": total_fetched,
            "new_inserted": new_inserted,
            "updated": updated,
            "failed": failed,
            "accounts_processed": len(accounts),
            "errors": errors,
        },
    }


@router.get("/{order_no}")
async def get_order_detail(
    order_no: str,
    refresh: bool = Query(default=False),
    current_user: User = Depends(deps.get_current_active_user),
    order_service: OrderService = Depends(deps.get_order_service),
):
    """获取订单详情，管理员可查看所有订单"""
    order = await order_service.get_order_by_id(order_no)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")

    # 验证订单属于当前用户（管理员可查看所有）
    _, is_admin = resolve_owner_scope(current_user)
    if not is_admin and order.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看此订单")
    
    if refresh and order.account_id:
        try:
            account_result = await order_service.session.execute(
                order_select(XYAccount).where(XYAccount.account_id == order.account_id)
            )
            account = account_result.scalar_one_or_none()
            if account and account.cookie:
                await OrderDetailService(order.account_id, account.cookie).fetch_and_update_order_detail(
                    order_id=order.order_no,
                    item_id=order.item_id,
                    buyer_id=order.buyer_id,
                )
                order_service.session.expire_all()
                order = await order_service.get_order_by_id(order_no)
        except Exception as e:
            logger.warning(f"刷新订单详情失败，返回本地数据: order_no={order_no}, error={e}")

    spec_parts = [part for part in [order.spec_name, order.spec_value] if part]
    sku_info = " / ".join(spec_parts) if spec_parts else None
    
    # 关联查询商品标题
    item_title = await order_service.get_item_title(order.owner_id, order.item_id)
    
    # 查询是否为代销订单
    from sqlalchemy import select as sa_select, func as sa_func
    from common.models.agent_order import AgentOrder
    agent_stmt = sa_select(sa_func.count(AgentOrder.id)).where(AgentOrder.order_no == order_no)
    agent_result = await order_service.session.execute(agent_stmt)
    is_agent_order = (agent_result.scalar() or 0) > 0

    # 关联自动发货消息日志，取最新发送状态与失败原因
    delivery_log_map = await order_service.get_delivery_log_status_map([order.order_no] if order.order_no else [])
    delivery_log = delivery_log_map.get(order.order_no) if order.order_no else None

    return {
        "success": True,
        "data": {
            "id": str(order.id),
            "order_id": order.order_no,
            "cookie_id": order.account_id or "",
            "item_id": order.item_id or "",
            "item_title": item_title,
            "buyer_id": order.buyer_id or "",
            "buyer_fish_nick": order.buyer_fish_nick or "",
            "chat_id": order.chat_id or "",
            "spec_name": order.spec_name or "",
            "spec_value": order.spec_value or "",
            "sku_info": sku_info,
            "quantity": order.quantity or 0,
            "amount": _format_decimal(order.amount),
            "status": (order.status or "unknown").lower(),
            "is_bargain": order.is_bargain or False,
            "is_rated": order.is_rated or False,
            "is_red_flower": order.is_red_flower or False,
            "receiver_name": order.receiver_name or "",
            "receiver_phone": order.receiver_phone or "",
            "receiver_address": order.receiver_address or "",
            "delivery_method": order.delivery_method or "",
            "delivery_content": order.delivery_content or "",
            "delivery_fail_reason": order.delivery_fail_reason or "",
            "delivery_send_status": (delivery_log or {}).get("send_status"),
            "delivery_send_fail_reason": (delivery_log or {}).get("send_fail_reason"),
            "is_agent_order": is_agent_order,
            "source": order.source or "",
            "placed_at": safe_isoformat(order.placed_at),
            "created_at": safe_isoformat(order.created_at),
            "updated_at": safe_isoformat(order.updated_at),
        }
    }


@router.post("/batch-delete")
async def batch_delete_orders(
    request: BatchDeleteOrdersRequest,
    current_user: User = Depends(deps.get_current_active_user),
    order_service: OrderService = Depends(deps.get_order_service),
):
    """批量删除订单"""
    if not request.ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要删除的订单")

    owner_id, _ = resolve_owner_scope(current_user)

    result = await order_service.batch_delete_orders(request.ids, owner_id)
    return {
        "success": True,
        "message": f"删除完成，成功{result['deleted']}条" + (f"，失败{result['failed']}条" if result['failed'] else ""),
        "data": result,
    }


@router.delete("/{order_id}")
async def delete_order(
    order_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    order_service: OrderService = Depends(deps.get_order_service),
):
    """删除订单"""
    success = await order_service.delete_order(order_id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在或无权删除")
    return ApiResponse(success=True, message="删除成功")


@router.post("/no-logistics-delivery")
async def no_logistics_delivery(
    request: NoLogisticsDeliveryRequest,
    current_user: User = Depends(deps.get_current_active_user),
    order_service: OrderService = Depends(deps.get_order_service),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """无物流发货：仅在闲鱼确认发货，不发送任何卡券或聊天内容"""
    order = await order_service.get_order_by_no(request.order_no)
    if not order:
        return ApiResponse(success=False, message="订单不存在")

    owner_id, is_admin = resolve_owner_scope(current_user)
    if not is_admin and order.owner_id != current_user.id:
        return ApiResponse(success=False, message="无权操作此订单")
    if order.status not in {"pending_ship", "pending", "paid", "待发货"}:
        return ApiResponse(success=False, message="只有待发货订单可以发货")
    if not order.account_id or not order.item_id or not order.buyer_id:
        return ApiResponse(success=False, message="订单缺少账号、商品或买家信息")

    account = await account_service.get_account_for_user(owner_id, order.account_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")

    status_result = await websocket_client.get_account_status(order.account_id)
    if not status_result.get("success") or not status_result.get("data", {}).get("is_connected"):
        return ApiResponse(success=False, message="账号未连接，请先启动账号")

    result = await websocket_client.confirm_no_logistics(
        account_id=order.account_id,
        order_no=order.order_no,
        item_id=order.item_id,
        buyer_id=order.buyer_id,
        is_bargain=bool(order.is_bargain),
    )
    if not result.get("success"):
        return ApiResponse(success=False, message=result.get("message", "无物流发货失败"))
    return ApiResponse(success=True, message="无物流发货成功", data=result.get("data"))


@router.post("/cancel")
async def cancel_order(
    request: CancelOrderRequest,
    current_user: User = Depends(deps.get_current_active_user),
    order_service: OrderService = Depends(deps.get_order_service),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """卖家关闭（取消）一笔待处理订单"""
    order = await order_service.get_order_by_no(request.order_no)
    if not order:
        return ApiResponse(success=False, message="订单不存在")
    owner_id, is_admin = resolve_owner_scope(current_user)
    if not is_admin and order.owner_id != current_user.id:
        return ApiResponse(success=False, message="无权操作此订单")
    if order.status not in {"pending_payment", "pending_ship", "pending", "paid", "待付款", "待发货"}:
        return ApiResponse(success=False, message="当前订单状态不可取消")
    if not order.account_id:
        return ApiResponse(success=False, message="订单缺少账号信息")
    if not await account_service.get_account_for_user(owner_id, order.account_id):
        return ApiResponse(success=False, message="账号不存在")

    status_result = await websocket_client.get_account_status(order.account_id)
    if not status_result.get("success") or not status_result.get("data", {}).get("is_connected"):
        return ApiResponse(success=False, message="账号未连接，请先启动账号")
    result = await websocket_client.cancel_order(order.account_id, order.order_no)
    if not result.get("success"):
        return ApiResponse(success=False, message=result.get("message", "取消订单失败"))
    return ApiResponse(success=True, message="订单已取消", data=result.get("data"))


@router.post("/manual-delivery")
async def manual_delivery(
    request: ManualDeliveryRequest,
    current_user: User = Depends(deps.get_current_active_user),
    order_service: OrderService = Depends(deps.get_order_service),
    account_service: AccountService = Depends(deps.get_account_service),
    card_service: CardService = Depends(deps.get_card_service),
):
    """手动发货
    
    通过WebSocket服务发送卡券给买家
    """
    try:
        logger.info(f"开始手动发货: order_no={request.order_no}")
        
        # 获取订单信息
        order = await order_service.get_order_by_no(request.order_no)
        if not order:
            logger.warning(f"订单不存在: {request.order_no}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
        
        logger.info(f"订单信息: account_id={order.account_id}, item_id={order.item_id}, chat_id={order.chat_id}, buyer_id={order.buyer_id}")
        
        # 管理员可以操作所有订单，普通用户只能操作自己的订单
        owner_id, is_admin = resolve_owner_scope(current_user)
        if not is_admin and order.owner_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作此订单")
        
        # 检查必要字段（chat_id 允许为空，后面会自动创建会话）
        if not order.account_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="订单缺少账号信息")
        if not order.item_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="订单缺少商品信息")
        if not order.buyer_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="订单缺少买家信息")
        
        # 获取账号信息（管理员可以操作所有账号）
        account = await account_service.get_account_for_user(owner_id, order.account_id)
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
        
        # 如果订单来源是"获取闲鱼订单"按钮，发货前先调用订单详情API刷新小刀状态
        if order.source == 'fetch_xianyu':
            try:
                from common.services.order_service import OrderDetailService
                cookies_str = account.cookie if hasattr(account, 'cookie') else ''
                if cookies_str:
                    detail_service = OrderDetailService(order.account_id, cookies_str)
                    await detail_service.fetch_and_update_order_detail(
                        order_id=order.order_no,
                        item_id=order.item_id,
                        buyer_id=order.buyer_id
                    )
                    # 重新获取订单（小刀状态可能已更新）
                    order = await order_service.get_order_by_no(request.order_no)
                    logger.info(f"订单详情已刷新: order_no={request.order_no}, is_bargain={order.is_bargain}")
                else:
                    logger.warning(f"账号 {order.account_id} 缺少cookies，跳过订单详情刷新")
            except Exception as e:
                logger.warning(f"刷新订单详情失败（不影响发货流程）: {e}")

        # 检查账号WebSocket连接状态
        from app.services.websocket_client import websocket_client
        status_result = await websocket_client.get_account_status(order.account_id)
        if not status_result.get('success') or not status_result.get('data', {}).get('is_connected'):
            logger.warning(f"账号未连接: {order.account_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号未连接，请先启动账号")
        
        # 如果订单缺少 chat_id，先调用闲鱼创建会话接口获取，然后回写到订单
        # 通过 LWP /r/SingleChatConversation/create 幂等创建，已存在会直接返回现有 cid
        if not order.chat_id:
            logger.info(
                f"订单 {request.order_no} 缺少 chat_id，开始自动创建会话: "
                f"account_id={order.account_id}, buyer_id={order.buyer_id}, item_id={order.item_id}"
            )
            create_result = await websocket_client.create_chat(
                account_id=order.account_id,
                buyer_id=order.buyer_id,
                item_id=order.item_id,
            )
            if not create_result.get('success'):
                err_msg = create_result.get('message', '创建会话失败')
                logger.error(f"自动创建会话失败: order_no={request.order_no}, 错误={err_msg}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"订单缺少会话ID且自动创建失败: {err_msg}",
                )
            new_chat_id = (create_result.get('data') or {}).get('chat_id')
            if not new_chat_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="创建会话接口未返回有效的 chat_id",
                )
            # 持久化到订单表
            updated = await order_service.update_order_chat_id(request.order_no, new_chat_id)
            if not updated:
                logger.warning(f"回写订单 chat_id 失败，但本次发货流程继续使用新 chat_id: {new_chat_id}")
            # 同步内存对象属性（session 配置 expire_on_commit=False，
            # commit 后 identity map 仍持有旧实例，重查会命中缓存拿不到新值）
            order.chat_id = new_chat_id
            logger.info(f"订单 {request.order_no} 已自动补写 chat_id={new_chat_id}")
        
        # 获取卡券
        spec_name = order.spec_name
        spec_value = order.spec_value
        logger.info(f"查询卡券: item_id={order.item_id}, spec_name={spec_name}, spec_value={spec_value}")
        
        cards = await card_service.get_cards_by_item_id_and_spec(order.item_id, spec_name, spec_value)
        logger.info(f"匹配到 {len(cards)} 个卡券")
        
        if not cards:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到匹配的卡券，请先配置发货卡券")
        
        if len(cards) > 1:
            card_names = [c.get('name') for c in cards]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"匹配到{len(cards)}个卡券({', '.join(card_names)})，需要唯一匹配"
            )
        
        card = cards[0]
        card_type = card.get('type')
        logger.info(f"使用卡券: {card.get('name')} ({card_type})")
        
        # 调用WebSocket服务的内部API进行发货
        # 传递订单信息和卡券信息给WebSocket服务
        # quantity 从订单表读取，>1 时让 internal API 循环发送 N 张卡券（多数量发货）
        delivery_result = await websocket_client.deliver_order(
            account_id=order.account_id,
            order_no=request.order_no,
            item_id=order.item_id,
            buyer_id=order.buyer_id,
            chat_id=order.chat_id,
            card_id=card.get('id'),
            is_bargain=order.is_bargain or False,
            delivery_method="manual",
            quantity=int(order.quantity) if order.quantity and order.quantity > 0 else 1,
        )
        
        if not delivery_result.get('success'):
            error_msg = delivery_result.get('message', '发货失败')
            logger.error(f"发货失败: {error_msg}")
            # 并发占用提示不算发货失败，不记录失败原因
            if "订单正在被其他进程处理" not in error_msg:
                # 将失败原因记录到订单表
                try:
                    await order_service.update_order_delivery_fail_reason(
                        request.order_no, error_msg
                    )
                except Exception as rec_err:
                    logger.warning(f"记录发货失败原因到订单表失败: {rec_err}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg)

        # 更新订单状态
        # is_card_only=True 表示 internal API 走了「禁止发货 + 主动关闭订单 + 仅发卡券」流程：
        # 订单已被卖家在闲鱼平台主动关闭，本地状态应保持原状，
        # 由后续闲鱼订单状态同步任务（check_can_ship 等）自然回写为关闭状态，
        # 这里若强制改为 'shipped' 会与闲鱼平台真实状态冲突，且会清空 delivery_fail_reason
        # 中由 pre_check 写入的禁止发货原因。
        delivery_data = delivery_result.get('data') or {}
        is_card_only = bool(delivery_data.get('is_card_only'))
        skipped_due_to_dock = bool(delivery_data.get('skipped_due_to_dock_card'))
        # 多数量退化标记：订单 quantity>1 但因卡券类型限制只发了 1 张，
        # 写入 delivery_fail_reason 提醒商家原因和后续动作
        quantity_degraded_for_dock = bool(delivery_data.get('quantity_degraded_for_dock_card'))
        quantity_degraded_for_fixed = bool(delivery_data.get('quantity_degraded_for_fixed_content'))
        degraded_warn_msg = None
        if quantity_degraded_for_dock:
            requested = delivery_data.get('quantity_requested') or order.quantity or 1
            sent = delivery_data.get('quantity_sent') or 1
            degraded_warn_msg = (
                f"⚠️ 对接卡券暂不支持多数量发货：订单数量 {requested} 张，"
                f"已发送 {sent} 张，剩余 {max(requested - sent, 0)} 张请手动补发或改用自有卡券"
            )
        elif quantity_degraded_for_fixed:
            requested = delivery_data.get('quantity_requested') or order.quantity or 1
            sent = delivery_data.get('quantity_sent') or 1
            degraded_warn_msg = (
                f"⚠️ 固定内容卡券（{delivery_data.get('delivery_type')} 类型）不支持多数量发货："
                f"订单数量 {requested} 张，仅发送 1 张固定内容（剩余 {max(requested - sent, 0)} 张未发）。"
                f"如需多数量发送不同卡密，请改用 data 或 api 类型卡券"
            )

        if degraded_warn_msg:
            try:
                await order_service.update_order_delivery_fail_reason(order.order_no, degraded_warn_msg)
                logger.warning(f"手动发货：订单 {order.order_no} {degraded_warn_msg}")
            except Exception as warn_err:
                logger.warning(
                    f"手动发货：订单 {order.order_no} 写入多数量退化提示失败: {warn_err}"
                )

        # 订单状态写入由 internal API 内部统一处理（card_only 走 record_delivery_for_closed_order，
        # 正常路径走 update_order_delivery_info(status='shipped')，多数量场景下 delivery_content
        # 是 \n--- 合并后的 N 张卡密内容）。这里不再重复写入：
        #   - 重复写入会引发并发覆盖
        #   - 历史代码在外层读取 delivery_data.get('delivery_content') 但 internal API 实际返回的是
        #     'content'，会把内层写好的 delivery_content 反向覆盖为空字符串
        if is_card_only:
            if skipped_due_to_dock:
                logger.warning(
                    f"手动发货：订单 {request.order_no} card_only + 对接卡券，"
                    f"订单已被关闭但卡券未发送（避免货主财务损失）"
                )
            else:
                logger.info(
                    f"手动发货：订单 {request.order_no} card_only 模式，"
                    f"订单已在闲鱼平台被关闭，仅补发卡券，本地状态保持不变（以闲鱼为准）"
                )

        logger.info(f"手动发货完成: 订单={request.order_no}, 卡券={card.get('name')}, "
                    f"is_card_only={is_card_only}, skipped_due_to_dock={skipped_due_to_dock}")

        # 直接复用 internal API 已生成的 message，它已经覆盖了所有场景的精确文案：
        # - 普通成功：「发货成功（共 N 张）」
        # - card_only：「card_only 模式：仅补发卡券（共 N 张），订单已被关闭」
        # - 退化：「对接卡券暂不支持多数量发货...」/「固定内容卡券不支持多数量发货...」
        # - 部分异常：「发货成功（共 2 张）（⚠️ 仅发出 2/3 张...）」
        # 旧代码自己拼 "发货成功" 会吞掉退化和部分异常提示，导致前端弹窗与订单 fail_reason 不一致。
        # 仅 skipped_due_to_dock（card_only + 对接卡券保护）这个 backend-web 视角的特殊文案保留本地拼接。
        if skipped_due_to_dock:
            response_message = "订单已被关闭，但因对接卡券保护跳过发送（避免货主财务损失，请使用自有卡券）"
        else:
            response_message = delivery_result.get('message') or "发货成功"

        return {
            "success": True,
            "message": response_message,
            "data": {
                "order_no": request.order_no,
                "card_name": card.get('name'),
                "card_type": card_type,
                **delivery_data
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"手动发货失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"发货失败: {str(e)}")
