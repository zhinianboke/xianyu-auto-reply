"""
禁止发货规则元信息（前端展示用）

功能：
1. 定义所有可用规则的元信息（编码、名称、描述、默认参数、默认优先级）
2. 供 backend-web 和 websocket 两个服务共同使用
3. 新增规则时在此处注册元信息即可
"""
from __future__ import annotations

from typing import Any


# 所有可用规则的元信息定义
# 新增规则只需在此列表追加一项
DELIVERY_BLOCK_RULE_METADATA: list[dict[str, Any]] = [
    {
        "rule_code": "buyer_credit_zero",
        "rule_name": "买家信用度检查",
        "rule_description": "检查买家被评价总数，评价数为0（或低于设定阈值）时禁止发货",
        "default_config": {"threshold": 0},
        "default_priority": 10,
    },
    {
        "rule_code": "buyer_has_order",
        "rule_name": "买家已有订单",
        "rule_description": "检查买家在当前卖家下是否已有其他订单，有则禁止发货",
        "default_config": {"same_item_only": False},
        "default_priority": 20,
    },
    {
        "rule_code": "buyer_has_order_global",
        "rule_name": "买家在同用户其他账号已有订单",
        "rule_description": "检查买家在当前用户名下所有账号中是否已有其他订单，有则禁止发货",
        "default_config": {"same_item_only": False},
        "default_priority": 25,
    },
    {
        "rule_code": "buyer_unconfirmed",
        "rule_name": "买家存在未确认收货订单",
        "rule_description": "检查买家在当前卖家下是否有未确认收货的订单，有则禁止发货",
        "default_config": {"min_count": 1, "same_item_only": False},
        "default_priority": 30,
    },
    {
        "rule_code": "personal_blacklist",
        "rule_name": "个人黑名单",
        "rule_description": "检查买家是否在个人黑名单中（支持商品级、账户级、用户级匹配）",
        "default_config": {},
        "default_priority": 5,
    },
]


def get_all_rule_metadata() -> list[dict[str, Any]]:
    """获取所有已注册规则的元信息（前端展示用）

    Returns:
        按默认优先级排序的规则元信息列表
    """
    result = sorted(DELIVERY_BLOCK_RULE_METADATA, key=lambda x: x["default_priority"])
    return result


def get_rule_default_priority(rule_code: str) -> int:
    """获取规则的默认优先级

    Args:
        rule_code: 规则编码

    Returns:
        默认优先级，未找到返回 99
    """
    for meta in DELIVERY_BLOCK_RULE_METADATA:
        if meta["rule_code"] == rule_code:
            return meta["default_priority"]
    return 99
