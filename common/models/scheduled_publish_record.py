"""
定时发布记录模型。

功能：
1. 记录定时发布规则每次实际发布尝试；
2. 保存发布结果和失败原因；
3. 为成功素材排除和当天是否已尝试发布提供依据。
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ScheduledPublishRecord(TimestampMixin, Base):
    """商品定时发布记录表。"""

    __tablename__ = "xy_scheduled_publish_records"
    __table_args__ = (
        Index("idx_sprr_rule_account_date", "rule_id", "account_id", "publish_date"),
        Index(
            "idx_sprr_success_material",
            "rule_id",
            "account_id",
            "publish_result",
            "material_id",
        ),
        Index("idx_sprr_owner_date", "owner_id", "publish_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="所属用户ID")
    rule_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="定时发布规则ID")
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, comment="闲鱼账号ID")
    material_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="商品素材ID，无可用素材时为空",
    )
    publish_result: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="发布结果：success-成功，failure-失败",
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, comment="失败原因")
    publish_date: Mapped[date] = mapped_column(Date, nullable=False, comment="发布日期（北京时间）")
