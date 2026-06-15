"""
商品上新监控任务模型

功能：
1. 定义上新监控任务表结构（xy_listing_monitor_tasks）
2. 记录监控关键字、价格区间、任务间隔与关联账号
3. 支持多用户数据隔离（owner_id）与软删除（is_deleted）
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ListingMonitorTask(TimestampMixin, Base):
    """商品上新监控任务表"""

    __tablename__ = "xy_listing_monitor_tasks"
    __table_args__ = (
        Index("idx_lmt_owner_enabled", "owner_id", "is_enabled"),
        Index("idx_lmt_owner_deleted", "owner_id", "is_deleted"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(BigInteger, index=True, comment="归属用户ID，用于多用户数据隔离")
    monitor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="listing", server_default="listing", comment="监控类型：listing-上新监控，price_drop-降价监控")
    keyword: Mapped[str] = mapped_column(String(200), nullable=False, comment="商品监控关键字")
    price_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), comment="商品价格区间最低值")
    price_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), comment="商品价格区间最高值")
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5", comment="任务执行间隔（分钟）")
    collect_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1", comment="每次采集页数")
    account_ids: Mapped[list | None] = mapped_column(JSON, comment="关联的闲鱼账号ID列表（JSON数组）")
    dm_account_id: Mapped[str | None] = mapped_column(String(80), comment="私信账号ID（单选，命中商品后用于私信）")
    dm_content: Mapped[str | None] = mapped_column(String(1000), comment="私信内容（填写私信账号后必填）")
    order_account_id: Mapped[str | None] = mapped_column(String(80), comment="下单账号ID（单选）")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1", comment="是否启用监控任务")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0", comment="是否已删除（软删除）")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最近一次执行时间")
    created_by: Mapped[int | None] = mapped_column(BigInteger, comment="创建人用户ID")
    remark: Mapped[str | None] = mapped_column(String(500), comment="备注")
