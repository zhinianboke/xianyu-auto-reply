"""
商品监控采集商品信息模型

功能：
1. 定义采集商品信息表结构（xy_listing_monitor_items）
2. 与商品监控任务（xy_listing_monitor_tasks）关联，记录每次采集到的商品
3. 通过 (monitor_task_id, item_id) 唯一约束区分新增与更新
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ListingMonitorItem(TimestampMixin, Base):
    """商品监控采集商品信息表"""

    __tablename__ = "xy_listing_monitor_items"
    __table_args__ = (
        UniqueConstraint("monitor_task_id", "item_id", name="uk_lmi_task_item"),
        Index("idx_lmi_task", "monitor_task_id"),
        Index("idx_lmi_owner", "owner_id"),
        Index("idx_lmi_publish_time", "publish_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    monitor_task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="关联的商品监控任务ID")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, comment="归属用户ID")
    item_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="闲鱼商品ID")
    title: Mapped[str | None] = mapped_column(String(500), comment="商品标题")
    price: Mapped[str | None] = mapped_column(String(32), comment="商品价格（展示文本）")
    area: Mapped[str | None] = mapped_column(String(120), comment="商品所在地区")
    pic_url: Mapped[str | None] = mapped_column(String(1000), comment="商品主图URL")
    seller_id: Mapped[str | None] = mapped_column(String(120), comment="卖家ID（搜索返回，可能为加密串）")
    seller_user_id: Mapped[str | None] = mapped_column(String(64), comment="卖家真实用户ID（商品详情接口补全）")
    seller_nick: Mapped[str | None] = mapped_column(String(120), comment="卖家昵称")
    want_count: Mapped[str | None] = mapped_column(String(32), comment="想要数")
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="商品发布时间")
    target_url: Mapped[str | None] = mapped_column(String(1000), comment="商品详情跳转URL")
    raw_json: Mapped[str | None] = mapped_column(Text, comment="商品原始数据（搜索结果项JSON，兜底）")
    detail_json: Mapped[str | None] = mapped_column(Text, comment="商品详情数据（详情接口返回JSON）")
    is_dm_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0", comment="是否已私信")
    is_ordered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0", comment="是否已下单")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最近一次采集到的时间")
