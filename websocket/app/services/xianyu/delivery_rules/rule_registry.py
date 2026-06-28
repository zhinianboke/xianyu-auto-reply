"""
规则注册表

功能：
1. 注册所有可用的禁止发货规则（实例化用）
2. 提供规则实例获取方法
3. 元信息查询委托给 common.services.delivery_block_rule_meta
"""
from __future__ import annotations

from typing import Any

from app.services.xianyu.delivery_rules.base_rule import BaseDeliveryRule
from app.services.xianyu.delivery_rules.buyer_credit_rule import BuyerCreditRule
from app.services.xianyu.delivery_rules.buyer_has_order_rule import BuyerHasOrderRule
from app.services.xianyu.delivery_rules.buyer_has_order_global_rule import BuyerHasOrderGlobalRule
from app.services.xianyu.delivery_rules.buyer_unconfirmed_rule import BuyerUnconfirmedRule
from app.services.xianyu.delivery_rules.personal_blacklist_rule import PersonalBlacklistRule


# 所有可用规则的注册表：rule_code -> 规则类
# 新增规则只需在此处注册即可
RULE_REGISTRY: dict[str, type[BaseDeliveryRule]] = {
    "buyer_credit_zero": BuyerCreditRule,
    "buyer_has_order": BuyerHasOrderRule,
    "buyer_has_order_global": BuyerHasOrderGlobalRule,
    "buyer_unconfirmed": BuyerUnconfirmedRule,
    "personal_blacklist": PersonalBlacklistRule,
}


def get_rule_instance(rule_code: str) -> BaseDeliveryRule | None:
    """根据规则编码获取规则实例

    Args:
        rule_code: 规则编码

    Returns:
        规则实例，未注册的编码返回 None
    """
    rule_cls = RULE_REGISTRY.get(rule_code)
    if rule_cls is None:
        return None
    return rule_cls()


def get_all_rule_metadata() -> list[dict[str, Any]]:
    """获取所有已注册规则的元信息（前端展示用）

    委托给 common 模块的共享实现。
    """
    from common.services.delivery_block_rule_meta import get_all_rule_metadata as _get_meta
    return _get_meta()
