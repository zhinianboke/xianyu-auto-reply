"""商品自动续售执行记录。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class AutoRelistEvent(Base):
    """记录一次成交触发的续售，提供幂等和审计能力。"""

    __tablename__ = "xy_auto_relist_events"
    __table_args__ = (
        UniqueConstraint("rule_id", "order_no", name="uk_auto_relist_rule_order"),
        Index("idx_auto_relist_event_due", "status", "next_retry_at"),
        Index("idx_auto_relist_event_user", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    rule_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    material_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False)
    old_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    new_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
