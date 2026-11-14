"""
xianyu_direct_payload 的网页后端兼容导出。

功能：
1. 保留原 app.services 导入路径；
2. 统一复用 common 中的实现，避免跨服务复制业务逻辑。
"""
from __future__ import annotations

from common.services.xianyu_direct_payload import (
    DirectPublishError,
    text,
    build_item_text_dto,
    price_in_cent,
    build_sku_payload,
    _build_sku_rows,
    extract_item_id_from_url,
    find_item_reference,
)

__all__ = [
    "DirectPublishError",
    "text",
    "build_item_text_dto",
    "price_in_cent",
    "build_sku_payload",
    "extract_item_id_from_url",
    "find_item_reference",
]
