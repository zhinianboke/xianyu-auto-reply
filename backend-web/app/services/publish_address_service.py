"""
商品发布随机地址池服务

功能：
1. 兼容 backend-web 原导入路径
2. 复用 common 公共地址池服务实现
"""
from __future__ import annotations

from common.services.publish_address_service import (
    PublishAddressQueueState,
    PublishAddressService,
    ResolvedPublishAddress,
    _address_to_dict,
)

__all__ = ["PublishAddressService", "ResolvedPublishAddress", "PublishAddressQueueState", "_address_to_dict"]
