from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class GoofishCrawlJob(TimestampMixin, Base):
    __tablename__ = "xy_goofish_crawl_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="归属用户ID")
    cookie_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False, comment="账号标识")

    keyword: Mapped[str] = mapped_column(String(80), nullable=False, comment="抓取关键词")
    interval_seconds: Mapped[int] = mapped_column(Integer, default=900, nullable=False, comment="执行间隔(秒)")

    start_page: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="起始页码")
    pages: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="抓取页数")
    page_size: Mapped[int] = mapped_column(Integer, default=20, nullable=False, comment="每页数量")
    fetch_detail: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否抓取详情")
    detail_limit: Mapped[int] = mapped_column(Integer, default=20, nullable=False, comment="抓取详情数量上限")

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否启用")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最近一次执行时间")
    last_error: Mapped[str | None] = mapped_column(Text, comment="最近一次错误信息")


