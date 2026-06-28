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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    job_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False, comment="关联的抓取任务ID")
    item_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="闲鱼商品ID")

    title: Mapped[str | None] = mapped_column(Text, comment="商品标题")
    price: Mapped[str | None] = mapped_column(String(64), comment="商品价格")
    area: Mapped[str | None] = mapped_column(String(120), comment="所在地区")
    seller_name: Mapped[str | None] = mapped_column(String(120), comment="卖家昵称")
    item_url: Mapped[str | None] = mapped_column(Text, comment="商品链接")
    main_image: Mapped[str | None] = mapped_column(String(512), comment="主图URL")
    publish_time: Mapped[str | None] = mapped_column(String(64), comment="发布时间")

    want_count: Mapped[int | None] = mapped_column(Integer, comment="想要人数")
    view_count: Mapped[int | None] = mapped_column(Integer, comment="浏览次数")

    description: Mapped[str | None] = mapped_column(Text, comment="商品描述")
    detail_error: Mapped[str | None] = mapped_column(String(255), comment="详情抓取错误信息")

    raw_json: Mapped[dict | None] = mapped_column(JSON, comment="原始数据JSON")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="抓取时间")

