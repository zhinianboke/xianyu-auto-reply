"""
禁止发货规则引擎

功能：
1. 定义规则基类和检查上下文
2. 注册所有可用规则
3. 提供规则加载和执行入口
"""
from app.services.xianyu.delivery_rules.base_rule import (
    BaseDeliveryRule,
    RuleCheckResult,
)
from app.services.xianyu.delivery_rules.context import DeliveryCheckContext
from app.services.xianyu.delivery_rules.rule_registry import (
    RULE_REGISTRY,
    get_rule_instance,
)

__all__ = [
    "BaseDeliveryRule",
    "RuleCheckResult",
    "DeliveryCheckContext",
    "RULE_REGISTRY",
    "get_rule_instance",
]
