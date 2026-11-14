"""
xianyu_item_snapshot 的网页后端兼容导出。

功能：
1. 保留原 app.services 导入路径；
2. 统一复用 common 中的实现，避免跨服务复制业务逻辑。
"""
from __future__ import annotations

from common.services.xianyu_item_snapshot import (
    as_bool,
    as_int,
    normalize_snapshot_image,
    normalize_snapshot_post_fee,
    shipping_method_from_post_fee,
    snapshot_post_fee_unchanged,
    snapshot_post_fee_shipping_unchanged,
    snapshot_address_if_unchanged,
    snapshot_image_index,
    normalize_snapshot_video,
    snapshot_video_items,
    snapshot_video_index,
    snapshot_user_rights,
)

__all__ = [
    "as_bool",
    "as_int",
    "normalize_snapshot_image",
    "normalize_snapshot_post_fee",
    "normalize_snapshot_video",
    "shipping_method_from_post_fee",
    "snapshot_address_if_unchanged",
    "snapshot_image_index",
    "snapshot_post_fee_unchanged",
    "snapshot_post_fee_shipping_unchanged",
    "snapshot_user_rights",
    "snapshot_video_index",
    "snapshot_video_items",
]
