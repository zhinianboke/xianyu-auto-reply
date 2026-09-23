"""公开订单查询服务。

该服务负责校验分销秘钥、限定用户数据范围，并复用订单查询服务完成分页查询。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.external_account_service import ExternalAccountService
from common.models.user import UserStatus
from common.services.order_service import OrderService
from common.utils.time_utils import safe_isoformat


class ExternalOrderAccessError(RuntimeError):
    """公开订单接口身份校验失败。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _format_amount(value: Any) -> str:
    """将订单金额格式化为稳定的字符串，避免浮点精度和 JSON Decimal 问题。"""
    if value is None:
        return "0.00"
    try:
        return format(value, "f")
    except (TypeError, ValueError):
        return str(value)


class ExternalOrderQueryService:
    """按公开接口身份查询订单。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _resolve_owner_id(self, secret_key: str) -> int:
        """根据分销秘钥解析可访问订单的用户 ID。"""
        user = await ExternalAccountService(self.session).get_user_by_secret(secret_key)
        if user is None:
            raise ExternalOrderAccessError(40001, "秘钥不存在")
        if user.status == UserStatus.DELETED:
            raise ExternalOrderAccessError(40001, "秘钥对应的用户不可用")
        return user.id

    @staticmethod
    def _serialize_order(
        order: Any,
        item_title: str,
        delivery_log: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """将订单模型转换为公开接口返回结构。"""
        spec_parts = [part for part in (order.spec_name, order.spec_value) if part]
        delivery_log = delivery_log or {}
        return {
            "id": str(order.id),
            "order_no": order.order_no,
            "order_id": order.order_no,
            "item_id": order.item_id or "",
            "item_title": item_title,
            "status": (order.status or "unknown").lower(),
            "buyer_id": order.buyer_id or "",
            "buyer_nick": order.buyer_nick or "",
            "buyer_fish_nick": order.buyer_fish_nick or "",
            "chat_id": order.chat_id or "",
            "spec_name": order.spec_name or "",
            "spec_value": order.spec_value or "",
            "sku_info": " / ".join(spec_parts) if spec_parts else "",
            "quantity": order.quantity or 0,
            "amount": _format_amount(order.amount),
            "currency": order.currency or "CNY",
            "account_id": order.account_id or "",
            "cookie_id": order.account_id or "",
            "account_name": order.account_name or "",
            "is_bargain": bool(order.is_bargain),
            "is_rated": bool(order.is_rated),
            "is_red_flower": bool(order.is_red_flower),
            "is_unregistered": bool(order.is_unregistered),
            "unregister_error_reason": order.unregister_error_reason or "",
            "receiver_name": order.receiver_name or "",
            "receiver_phone": order.receiver_phone or "",
            "receiver_address": order.receiver_address or "",
            "delivery_method": order.delivery_method or "",
            "delivery_content": order.delivery_content or "",
            "delivery_fail_reason": order.delivery_fail_reason or "",
            "card_only_delivered": bool(order.card_only_delivered),
            "delivery_send_status": delivery_log.get("send_status"),
            "delivery_send_fail_reason": delivery_log.get("send_fail_reason"),
            "source": order.source or "",
            "placed_at": safe_isoformat(order.placed_at),
            "synced_at": safe_isoformat(order.synced_at),
            "created_at": safe_isoformat(order.created_at),
            "updated_at": safe_isoformat(order.updated_at),
        }

    async def list_orders(
        self,
        secret_key: str,
        *,
        item_ids: list[str] | None = None,
        order_no: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """查询秘钥所属用户订单并返回分页结果。"""
        owner_id = await self._resolve_owner_id(secret_key.strip())
        order_service = OrderService(self.session)
        orders, total, item_titles = await order_service.list_orders(
            owner_id,
            item_ids=item_ids,
            order_no=order_no,
            page=page,
            page_size=page_size,
        )
        order_nos = [order.order_no for order in orders if order.order_no]
        delivery_logs = await order_service.get_delivery_log_status_map(order_nos)
        data = [
            self._serialize_order(
                order,
                item_titles.get(order.item_id, "") if order.item_id else "",
                delivery_logs.get(order.order_no),
            )
            for order in orders
        ]
        return {
            "list": data,
            "orders": data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }


__all__ = ["ExternalOrderAccessError", "ExternalOrderQueryService"]
