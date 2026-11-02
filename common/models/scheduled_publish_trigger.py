"""
定时发布触发记录模型。

功能：
1. 按规则和账号保存唯一的下次触发时间；
2. 记录最近初始化日期，保证每天仅首次扫描生成随机时间。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ScheduledPublishTrigger(TimestampMixin, Base):
    """商品定时发布触发记录表。"""

    __tablename__ = "xy_scheduled_publish_triggers"
    __table_args__ = (
        UniqueConstraint("owner_id", "rule_id", "account_id", name="uk_spt_owner_rule_account"),
        Index("idx_spt_next_trigger", "next_trigger_at"),
        Index("idx_spt_owner", "owner_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属用户ID")
    rule_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="定时发布规则ID")
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, comment="闲鱼账号ID")
    schedule_date: Mapped[date] = mapped_column(Date, nullable=False, comment="最近计划初始化日期（北京时间）")
    next_trigger_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        comment="下次触发时间（北京时间）",
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        comment="是否已删除（软删除）",
    )
