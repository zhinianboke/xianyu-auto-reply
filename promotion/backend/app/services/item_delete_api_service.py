"""返佣系统兼容入口，闲鱼商品删除实现统一复用公共服务。"""
from common.services.item_delete_service import (
    DELETE_ITEM_API,
    DELETE_ITEM_URL,
    MAX_NETWORK_RETRY,
    MAX_TOKEN_RETRY,
    REQUEST_TIMEOUT,
    delete_item_from_xianyu,
)


__all__ = [
    "DELETE_ITEM_API",
    "DELETE_ITEM_URL",
    "MAX_NETWORK_RETRY",
    "MAX_TOKEN_RETRY",
    "REQUEST_TIMEOUT",
    "delete_item_from_xianyu",
]
