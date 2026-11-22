"""卡券消费错误契约：配置失效与真实空库存必须区分，供各发货入口统一处理。"""
from __future__ import annotations


class CardConsumptionConfigurationError(RuntimeError):
    """取卡前或原子消费时配置失效；消息可直接用于发货中断告警。"""
