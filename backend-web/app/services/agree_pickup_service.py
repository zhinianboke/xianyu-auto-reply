"""
同意后发货 - 提货页服务（backend-web 公开层）

功能：
1. 校验提货页订单：按订单主键(orderId) + 订单号(orderNo) 双重校验
   （不存在 / 不匹配 均返回明确中文提示）
2. 买家点击「同意」：Redis 锁串行 + 幂等 → 调 websocket 内部接口触发真实发货并返回卡券内容
3. 回显商品信息：商品标题（商品表 xy_items，缺失时用自动回复日志记录的标题兜底）
   + 闲鱼商品详情页地址

说明：
- 本层为无认证公开接口的业务实现，仅读取展示所需的最小订单信息，不下发敏感字段。
- 实际的确认发货/免拼/取卡在 websocket 服务完成（需在线账号实例）。
- 跨进程并发（买家重复点击、与定时补发货争抢）由 Redis 发货锁保证串行。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.websocket_client import websocket_client
from common.db.redis_client import release_delivery_lock, try_acquire_delivery_lock
from common.models.xy_order import XYOrder
from common.services.order_service import OrderService
from common.utils.xianyu_utils import canonical_goofish_item_url


class AgreePickupService:
    """同意后发货提货页服务"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load_and_validate(
        self, order_no: str, order_id: str
    ) -> Tuple[bool, str, Optional[XYOrder]]:
        """按订单主键查订单并校验订单号匹配。返回 (ok, message, order)。

        order_id 以字符串入参并在此安全解析为整数，非法/缺失一律返回明确提示
        （遵循全站「无论成败均 HTTP 200，业务错误走响应体」约定，避免框架抛 422）。
        """
        order_no = (order_no or "").strip()
        try:
            order_pk = int(str(order_id).strip())
        except (TypeError, ValueError):
            order_pk = 0
        if not order_no or order_pk <= 0:
            return False, "链接无效，缺少订单参数", None
        result = await self.session.execute(select(XYOrder).where(XYOrder.id == order_pk))
        order = result.scalars().first()
        if not order:
            return False, "订单不存在", None
        if (order.order_no or "").strip() != order_no:
            return False, "订单号与订单id不匹配", None
        return True, "", order

    @staticmethod
    def _order_view(order: XYOrder, item_title: str = "") -> Dict[str, Any]:
        """提货页可展示的订单信息（最小必要字段）

        Args:
            order: 订单对象
            item_title: 商品标题（由调用方查商品表取得，取不到传空字符串）
        Returns:
            提货页展示字段字典
        """
        return {
            "order_no": order.order_no,
            "amount": str(order.amount) if order.amount is not None else None,
            "quantity": order.quantity,
            "spec_name": order.spec_name,
            "spec_value": order.spec_value,
            "item_id": order.item_id,
            # 标题取不到时前端退化展示商品ID，不展示空白
            "item_title": item_title or None,
            # 闲鱼商品详情页地址，供买家点击核对商品；无商品ID时为空
            "item_url": canonical_goofish_item_url(order.item_id) if order.item_id else None,
            "already_agreed": bool(order.agree_deliver_agreed),
            # 已同意时回显发货内容，未同意时不下发
            "content": order.delivery_content if order.agree_deliver_agreed else None,
        }

    async def query_order(
        self, order_no: str, order_id: str
    ) -> Tuple[bool, str, Optional[dict]]:
        """提货页加载：校验订单并返回展示信息 + 是否已同意/发货内容。"""
        ok, message, order = await self._load_and_validate(order_no, order_id)
        if not ok:
            return False, message, None
        # 商品标题复用公共订单服务的多来源解析（商品表 → 自动回复日志兜底，取不到返回空串）
        item_title = await OrderService(self.session).resolve_item_title(
            order.owner_id, order.item_id or ""
        )
        return True, "查询成功", self._order_view(order, item_title)

    async def agree(
        self, order_no: str, order_id: str
    ) -> Tuple[bool, str, Optional[dict]]:
        """买家点击「同意」：Redis 锁 + 幂等 → 调 websocket 触发发货并返回卡券内容。"""
        ok, message, order = await self._load_and_validate(order_no, order_id)
        if not ok:
            return False, message, None

        real_order_no = order.order_no

        # 幂等快速路径：已同意且已有内容，直接回显，不再触发发货
        if order.agree_deliver_agreed and order.delivery_content:
            return True, "您已同意发货，以下为发货内容", {
                "order_no": real_order_no,
                "content": order.delivery_content,
                "already_agreed": True,
            }

        # Redis 发货锁：与买家重复点击、定时补发货互斥（key 内部为 order:{order_no}）
        lock_result = await try_acquire_delivery_lock(
            real_order_no, expire=120, holder_info="agree_pickup", wait_timeout=5
        )
        if lock_result.is_locked_by_other:
            return False, "订单正在处理中，请稍后再试", None
        if lock_result.has_error:
            return False, "系统繁忙，请稍后再试", None
        if not lock_result.success:
            return False, "订单正在处理中，请稍后再试", None

        try:
            # 触发真实发货（websocket 侧再做本地锁 + 幂等，权威处理确认发货/免拼/取卡）
            resp = await websocket_client.agree_pickup_deliver(real_order_no)
            if not isinstance(resp, dict):
                return False, "发货失败，请稍后重试或联系卖家", None
            success = bool(resp.get("success"))
            msg = resp.get("message") or ("发货成功" if success else "发货失败，请稍后重试或联系卖家")
            return success, msg, resp.get("data")
        finally:
            await release_delivery_lock(lock_result)
