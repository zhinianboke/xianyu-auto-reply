"""
禁止发货规则基类

功能：
1. 定义规则检查结果数据类 RuleCheckResult
2. 定义规则基类 BaseDeliveryRule，所有具体规则继承此类
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.services.xianyu.delivery_rules.context import DeliveryCheckContext


@dataclass
class RuleCheckResult:
    """规则检查结果"""

    # 是否命中（True=应拦截）
    hit: bool

    # 规则编码
    rule_code: str

    # 规则中文名称
    rule_name: str

    # 命中原因描述（写入订单 delivery_fail_reason）
    reason: str = ""

    # 附加数据（如评价数、订单数等，供日志/前端展示）
    extra_data: dict[str, Any] = field(default_factory=dict)


class BaseDeliveryRule(ABC):
    """禁止发货规则基类，所有规则继承此类实现 check 方法"""

    @property
    @abstractmethod
    def rule_code(self) -> str:
        """规则唯一编码（存数据库用）"""
        ...

    @property
    @abstractmethod
    def rule_name(self) -> str:
        """规则中文名称"""
        ...

    @property
    def rule_description(self) -> str:
        """规则描述（前端展示用）"""
        return ""

    @property
    def default_config(self) -> dict[str, Any]:
        """规则默认参数配置（前端初始化用）"""
        return {}

    @abstractmethod
    async def check(self, context: DeliveryCheckContext) -> RuleCheckResult:
        """执行规则检查

        只负责判断是否命中，不负责执行拦截动作（发消息/关单等由引擎统一处理）。

        Args:
            context: 发货检查上下文，包含订单、买家、卖家等信息

        Returns:
            RuleCheckResult: 检查结果
        """
        ...
