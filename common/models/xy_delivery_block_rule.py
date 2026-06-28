"""
禁止发货规则配置模型

功能：
1. 定义禁止发货规则配置表结构（xy_delivery_block_rules）
2. 每条规则独立拥有：开关、原因、主动关闭订单、关闭后只发卡券、排除商品列表、规则专属参数
3. 每个账号可配置多条规则，按 priority 排序执行，首条命中即停
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Boolean, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class XYDeliveryBlockRule(TimestampMixin, Base):
    """禁止发货规则配置表"""

    __tablename__ = "xy_delivery_block_rules"
    __table_args__ = (
        UniqueConstraint("account_id", "rule_code", name="uk_account_rule"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")

    # 账号标识（对应 xy_accounts.account_id）
    account_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="账号ID"
    )

    # 规则编码（唯一标识规则类型）
    rule_code: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="规则编码"
    )

    # 规则开关
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="规则开关"
    )

    # 执行优先级（越小越先执行）
    priority: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="执行优先级（越小越先执行）"
    )

    # 禁止发货原因（发给买家的消息）
    block_reason: Mapped[str | None] = mapped_column(
        String(500), default=None, comment="禁止发货原因（发给买家的消息）"
    )

    # 命中后主动关闭订单
    auto_close_order: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="命中后主动关闭订单"
    )

    # 关闭订单后继续发货（只发卡券）
    only_card_after_close: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="关闭订单后继续发货（只发卡券）"
    )

    # 该规则的排除商品列表（JSON 数组存储 item_id）
    excluded_item_ids: Mapped[list[str] | None] = mapped_column(
        JSON, default=None, comment="该规则的排除商品列表（命中则跳过本规则）"
    )

    # 规则专属参数（不同规则有不同配置项）
    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None, comment="规则专属参数"
    )
