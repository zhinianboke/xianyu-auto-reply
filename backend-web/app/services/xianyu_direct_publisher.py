"""
xianyu_direct_publisher 的网页后端兼容导出。

功能：
1. 保留原 app.services 导入路径；
2. 统一复用 common 中的实现，避免跨服务复制业务逻辑。
"""
from __future__ import annotations

from common.services.xianyu_direct_publisher import (
    PUBLISH_API,
    SELLER_ORIGIN,
    SELLER_REFERER,
    XianyuDirectPublisher,
    DirectPublishError,
)

__all__ = [
    "DirectPublishError",
    "XianyuDirectPublisher",
]
