"""
商品监控执行日志模型

功能：
1. 定义商品监控执行日志表结构（xy_listing_monitor_logs）
2. 记录每次监控任务执行的获取数、插入数、更新数与执行结果
3. 仅关联监控任务，不与采集商品表关联
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ListingMonitorLog(TimestampMixin, Base):
    """商品监控执行日志表"""

    __tablename__ = "xy_listing_monitor_logs"
    __table_args__ = (
        Index("idx_lml_task", "monitor_task_id"),
        Index("idx_lml_owner", "owner_id"),
        Index("idx_lml_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    monitor_task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="关联的商品监控任务ID")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, comment="归属用户ID")
    monitor_type: Mapped[str | None] = mapped_column(String(20), comment="监控类型：listing-上新监控，price_drop-降价监控")
    keyword: Mapped[str | None] = mapped_column(String(200), comment="监控关键字")
    trigger_type: Mapped[str] = mapped_column(String(10), nullable=False, default="auto", server_default="auto", comment="触发方式：auto-定时自动，manual-手动")
    account_id: Mapped[str | None] = mapped_column(String(80), comment="本次实际使用的主账号ID")
    used_account_ids: Mapped[list | None] = mapped_column(JSON, comment="本次执行实际使用过的账号ID列表（可能多个）")
    pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="本次采集页数")
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="本次获取的商品数")
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="本次新增的商品数")
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="本次更新的商品数")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success", server_default="success", comment="执行状态：success-成功，failed-失败，partial-部分成功")
    message: Mapped[str | None] = mapped_column(String(1000), comment="执行结果说明")
