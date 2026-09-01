"""商品售罄自动续售规则。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class AutoRelistRule(Base):
    """一份商品素材对应一条自动续售规则。"""

    __tablename__ = "xy_auto_relist_rules"
    __table_args__ = (
        UniqueConstraint("material_id", name="uk_auto_relist_material"),
        Index("idx_auto_relist_enabled_due", "enabled", "next_retry_at"),
        Index("idx_auto_relist_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    material_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    current_item_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    card_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="disabled")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_order_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_old_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_new_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_relisted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
