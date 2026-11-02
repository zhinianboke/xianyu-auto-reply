"""
定时发布规则模型。

功能：
1. 保存用户选择的闲鱼账号和商品素材；
2. 保存每日触发时间范围及随机发布间隔；
3. 保存规则启用状态，供定时发布任务筛选执行。
"""
from __future__ import annotations

from datetime import time

from sqlalchemy import BigInteger, Boolean, Index, Integer, JSON, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ScheduledPublishRule(TimestampMixin, Base):
    """商品定时发布规则表。"""

    __tablename__ = "xy_scheduled_publish_rules"
    __table_args__ = (
        Index("idx_spr_owner_created", "owner_id", "created_at"),
        Index("idx_spr_owner_name", "owner_id", "rule_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="规则ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="所属用户ID")
    rule_name: Mapped[str] = mapped_column(String(120), nullable=False, comment="规则名称")
    account_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, comment="闲鱼账号ID列表")
    material_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, comment="商品素材ID列表")
    trigger_start_time: Mapped[time] = mapped_column(Time, nullable=False, comment="每日触发开始时间")
    trigger_end_time: Mapped[time] = mapped_column(Time, nullable=False, comment="每日触发结束时间")
    interval_min_minutes: Mapped[int] = mapped_column(Integer, nullable=False, comment="随机间隔最小分钟数")
    interval_max_minutes: Mapped[int] = mapped_column(Integer, nullable=False, comment="随机间隔最大分钟数")
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
        comment="是否启用",
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        comment="是否已删除（软删除）",
    )
