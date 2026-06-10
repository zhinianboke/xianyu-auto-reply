"""
在线聊天(新) - 客户订单 API 路由

功能：
1. 查询某账号下指定买家（会话对方）的近期订单列表，供聊天工作台右侧订单面板展示

与 chat_new.py 共用同一 prefix="/chat-new"，按功能拆分为独立 router 以控制单文件体积。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db_session
from common.models import User, XYAccount, XYOrder
from common.schemas.common import ApiResponse
from common.services.order_service import OrderService
from common.utils.auth_scope import is_admin_user


router = APIRouter(prefix="/chat-new")


@router.get("/customer-orders/{account_id}/{buyer_id}")
async def get_customer_orders(
    account_id: str,
    buyer_id: str,
    chat_id: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """查询指定账号下某买家的近期订单（最多 20 条，按下单时间倒序）"""
    account_query = select(XYAccount).where(XYAccount.account_id == account_id)
    if not is_admin_user(current_user):
        account_query = account_query.where(XYAccount.owner_id == current_user.id)
    account = (await db.execute(account_query)).scalar_one_or_none()
    if not account:
        return ApiResponse(success=False, message="账号不存在或无权操作")

    # 按买家ID匹配；若提供了会话ID则一并按会话匹配，扩大命中范围
    customer_match = [XYOrder.buyer_id == buyer_id]
    if chat_id:
        customer_match.append(XYOrder.chat_id == chat_id)
    result = await db.execute(
        select(XYOrder)
        .where(
            XYOrder.owner_id == account.owner_id,
            XYOrder.account_id == account_id,
            or_(*customer_match),
        )
        .order_by(XYOrder.placed_at.desc(), XYOrder.created_at.desc())
        .limit(20)
    )
    orders = result.scalars().all()
    order_service = OrderService(db)
    data = []
    for order in orders:
        item_title = await order_service.get_item_title(order.owner_id, order.item_id) if order.item_id else ""
        data.append({
            "order_no": order.order_no,
            "item_id": order.item_id or "",
            "item_title": item_title or order.item_id or "未知商品",
            "buyer_id": order.buyer_id or "",
            "quantity": order.quantity or 1,
            "amount": str(order.amount) if order.amount is not None else "",
            "status": order.status or "unknown",
            "delivery_method": order.delivery_method or "",
            "delivery_fail_reason": order.delivery_fail_reason or "",
            "placed_at": order.placed_at.isoformat() if order.placed_at else "",
        })
    return ApiResponse(success=True, data=data)
