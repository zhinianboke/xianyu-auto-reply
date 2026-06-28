"""
商品监控分类模型

功能：
1. 定义商品监控分类表结构（xy_listing_monitor_categories）
2. 用于对监控任务进行分类管理（如：数码产品、服装鞋帽等）
3. 支持按分类配置兜底账号（采集账号、下单账号）
4. 支持多用户数据隔离（owner_id）与软删除（is_deleted）
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ListingMonitorCategory(TimestampMixin, Base):
    """商品监控分类表"""

    __tablename__ = "xy_listing_monitor_categories"
    __table_args__ = (
        Index("idx_lmc_owner", "owner_id"),
        Index("idx_lmc_owner_deleted", "owner_id", "is_deleted"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="归属用户ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="分类名称")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0", comment="是否已删除（软删除）")
