"""
个人发布地址库服务

功能：
1. 兼容 backend-web 原导入路径
2. 复用 common 公共个人地址库服务实现
"""
from __future__ import annotations

from common.services.user_publish_address_service import (
    UserPublishAddressService,
    _address_to_dict,
)

__all__ = ["UserPublishAddressService", "_address_to_dict"]
