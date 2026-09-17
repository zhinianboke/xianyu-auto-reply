"""自动续售共享工具。

集中处理素材发布载荷转换、北京时间归一化和发布幂等号生成，避免任务执行器重复实现。
"""
from __future__ import annotations

import hashlib
from typing import Any

from common.models.product_material import ProductMaterial
from common.utils.time_utils import BEIJING_TZ


def material_to_publish_data(material: ProductMaterial) -> dict[str, Any]:
    """将素材模型转换为公共发布服务载荷。"""
    shipping_method = material.shipping_method or ("fixed" if material.postage else "free")
    return {
        "id": material.id,
        "title": material.title,
        "description": material.description,
        "price": float(material.price or 0),
        "original_price": float(material.original_price) if material.original_price is not None else None,
        "category": material.category,
        "platform_category_id": material.platform_category_id,
        "platform_category_name": material.platform_category_name,
        "platform_channel_category_id": material.platform_channel_category_id,
        "platform_channel_category_name": material.platform_channel_category_name,
        "platform_leaf_id": material.platform_leaf_id,
        "platform_tb_category_id": material.platform_tb_category_id,
        "platform_category_path": material.platform_category_path or [],
        "platform_attributes": material.platform_attributes or [],
        "category_source": material.category_source or "manual",
        "category_confidence": float(material.category_confidence) if material.category_confidence is not None else None,
        "images": material.images or [],
        "videos": material.videos or [],
        "specifications": material.specifications or [],
        "sku_rows": material.sku_rows or [],
        "quantity": material.quantity or 1,
        # shipping_method 是实际发布依据；兼容历史素材中旧/空的 delivery_method。
        "delivery_method": "pickup" if shipping_method == "none" else "express",
        "shipping_method": shipping_method,
        "support_pickup": bool(material.support_pickup),
        "postage": float(material.postage or 0),
        "address": material.address,
        "address_expected_text": material.address_expected_text,
        "brand": material.brand,
        "condition": material.condition,
        "remark": material.remark,
    }


def naive_beijing(value):
    """将数据库返回的有时区时间统一为北京时间无时区值。"""
    if value is None:
        return None
    if getattr(value, "tzinfo", None):
        return value.astimezone(BEIJING_TZ).replace(tzinfo=None)
    return value


def build_publish_request_id(rule_id: int, order_no: str, old_item_id: str) -> str:
    """生成长度稳定的续售发布幂等号。"""
    digest = hashlib.sha256(f"{order_no}\0{old_item_id}".encode("utf-8")).hexdigest()[:32]
    return f"auto-relist:{rule_id}:{digest}"


def order_still_eligible(order: Any) -> bool:
    """判断订单当前状态是否仍满足自动续售触发条件。"""
    has_content = bool(str(order.delivery_content or "").strip())
    normal_delivery = (
        order.status in {"shipped", "completed"}
        and order.delivery_method == "auto"
        and has_content
    )
    card_only_delivery = (
        bool(order.card_only_delivered)
        and order.delivery_method in {"auto", "scheduled"}
        and has_content
        and order.status not in {"cancelled", "refunded", "refunding"}
    )
    return normal_delivery or card_only_delivery


__all__ = [
    "material_to_publish_data",
    "naive_beijing",
    "build_publish_request_id",
    "order_still_eligible",
]
