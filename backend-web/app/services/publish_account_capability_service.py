"""
publish_account_capability_service 的网页后端兼容导出。

功能：
1. 保留原 app.services 导入路径；
2. 统一复用 common 中的实现，避免跨服务复制业务逻辑。
"""
from __future__ import annotations

from common.services.publish_account_capability_service import (
    PREGET_API,
    PUBLISH_ORIGIN,
    PUBLISH_REFERER,
    BACKEND_PREGET_API,
    BACKEND_PREGET_DATA,
    SELLER_ORIGIN,
    SELLER_REFERER,
    SELLER_EXTRA_PARAMS,
    SELLER_EXTRA_HEADERS,
    _UNTRUSTED_FAILURE_MARKERS,
    _fallback_trust,
    _parse_capability,
    PublishAccountCapabilityService,
)

__all__ = [
    "PublishAccountCapabilityService",
]
