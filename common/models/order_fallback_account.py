"""
兜底下单账号配置模型

功能：
1. 定义用户级兜底下单账号配置表结构（xy_order_fallback_accounts）
2. 每个用户仅一条记录（owner_id 唯一），记录兜底使用的下单账号ID列表
3. 当监控任务自身的下单账号不可用（任务删除/禁用/未配置/账号失效）时，
   定时下单任务回退使用此处配置的账号下单
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class OrderFallbackAccount(TimestampMixin, Base):
    """用户级兜底下单账号配置表"""

    __tablename__ = "xy_order_fallback_accounts"
    __table_args__ = (
        # owner_id 唯一：保证一个用户只有一条兜底配置
        Index("uk_ofa_owner", "owner_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="归属用户ID（唯一，一个用户一条配置）")
    account_ids: Mapped[list | None] = mapped_column(JSON, comment="兜底下单账号ID列表（JSON数组，多选轮换使用）")
