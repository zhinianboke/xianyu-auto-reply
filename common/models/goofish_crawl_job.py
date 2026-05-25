from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class GoofishCrawlJob(TimestampMixin, Base):
    __tablename__ = "xy_goofish_crawl_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    cookie_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)

    keyword: Mapped[str] = mapped_column(String(80), nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=900, nullable=False)

    start_page: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    pages: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    page_size: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    fetch_detail: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    detail_limit: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


