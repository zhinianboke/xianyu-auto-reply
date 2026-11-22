"""卡券序列化公共方法，保留原有 API 字段和轻量列表行为。"""
from __future__ import annotations

import json
from typing import Any, Dict

from common.models.card import Card
from common.utils.time_utils import safe_isoformat


class CardSerializationMixin:
    """提供完整和轻量卡券字典转换方法。"""

    def _card_to_dict(self, card: Card) -> Dict[str, Any]:
        """转换预加载关联的卡券详情；参数为卡券对象，返回完整详情字典。"""
        data = self._card_to_dict_simple(card)
        data["item_ids"] = [relation.item_id for relation in card.item_relations]
        return data

    def _card_to_dict_lite(self, card: Card) -> Dict[str, Any]:
        """将卡券对象转换为轻量字典（仅列表/选择场景所需字段）。

        刻意剔除 text_content / data_content / api_config / image_urls 等大字段，
        用于「商品关联卡券」选择弹窗等需要一次性拉取全部卡券的场景，避免传输
        超大 JSON 拖慢界面。需要完整内容时请调用 get_card_by_id 按需获取。
        """
        return {
            "id": card.id,
            "user_id": card.user_id,
            "item_id": card.item_id,
            "name": card.name,
            "type": card.type,
            "enabled": card.enabled,
            "delay_seconds": card.delay_seconds,
            "use_no_logistics_form": card.use_no_logistics_form,
            "delivery_count": card.delivery_count,
            "price": card.price,
            "is_dockable": card.is_dockable,
            "fee_payer": card.fee_payer,
            "min_price": card.min_price,
            "dock_visibility": card.dock_visibility,
            "is_multi_spec": card.is_multi_spec,
            "spec_name": card.spec_name,
            "spec_value": card.spec_value,
            "created_at": safe_isoformat(card.created_at),
            "updated_at": safe_isoformat(card.updated_at),
        }

    def _card_to_dict_simple(self, card: Card) -> Dict[str, Any]:
        """复用轻量字段转换卡券内容；参数为卡券对象，返回不查询关联的完整字典。"""
        api_config = None
        if card.api_config:
            try:
                api_config = json.loads(card.api_config)
            except json.JSONDecodeError:
                api_config = card.api_config
        image_urls = None
        if card.image_urls:
            try:
                image_urls = json.loads(card.image_urls)
            except json.JSONDecodeError:
                image_urls = None
        return {
            **self._card_to_dict_lite(card),
            "description": card.description,
            "api_config": api_config,
            "text_content": card.text_content,
            "data_content": card.data_content,
            "image_url": card.image_url,
            "image_urls": image_urls,
        }
