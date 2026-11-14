"""
xianyu_item_payload_builder 的网页后端兼容导出。

功能：
1. 保留原 app.services 导入路径；
2. 统一复用 common 中的实现，避免跨服务复制业务逻辑。
"""
from __future__ import annotations

from common.services.xianyu_item_payload_builder import (
    MAX_IMAGE_COUNT,
    _location_to_gps,
    _address_match_score,
    _resolve_item_address,
    _build_category_label,
    _build_attribute_labels,
    _build_post_fee,
    _resolve_post_fee,
    _resolve_address,
    _resolve_quantity,
    _resolve_user_rights,
    build_item_payload,
    DirectPublishError,
)

__all__ = [
    "DirectPublishError",
    "build_item_payload",
]
