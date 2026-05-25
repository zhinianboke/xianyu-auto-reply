from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class GoofishCrawlItem(Base):
    __tablename__ = "xy_goofish_crawl_items"
    __table_args__ = (
        # 复合索引：加速按 (job_id, item_id) 去重检测
        Index("idx_crawl_job_item", "job_id", "item_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)

    title: Mapped[str | None] = mapped_column(Text)
    price: Mapped[str | None] = mapped_column(String(64))
    area: Mapped[str | None] = mapped_column(String(120))
    seller_name: Mapped[str | None] = mapped_column(String(120))
    item_url: Mapped[str | None] = mapped_column(Text)
    main_image: Mapped[str | None] = mapped_column(String(512))
    publish_time: Mapped[str | None] = mapped_column(String(64))

    want_count: Mapped[int | None] = mapped_column(Integer)
    view_count: Mapped[int | None] = mapped_column(Integer)

    description: Mapped[str | None] = mapped_column(Text)
    detail_error: Mapped[str | None] = mapped_column(String(255))

    raw_json: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

