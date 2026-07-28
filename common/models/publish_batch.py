"""商品批量发布任务模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class PublishBatch(TimestampMixin, Base):
    """持久化批量发布请求，提供跨进程幂等与恢复查询。"""

    __tablename__ = "xy_publish_batches"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uk_publish_batch_user_request"),
        Index("idx_publish_batch_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    account_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    material_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(1000))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
