"""
兜底下单账号配置模型

功能：
1. 定义用户级兜底下单账号配置表结构（xy_order_fallback_accounts）
2. 每个用户每个分类一条记录（owner_id, category_id 联合唯一）
3. 当监控任务自身的下单账号不可用（任务删除/禁用/未配置/账号失效）时，
   定时下单任务回退使用此处配置的账号下单
4. category_id = NULL 表示"未分类"的全局兜底账号
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class OrderFallbackAccount(TimestampMixin, Base):
    """用户级兜底下单账号配置表（按分类配置）"""

    __tablename__ = "xy_order_fallback_accounts"
    __table_args__ = (
        Index("uk_ofa_owner_category", "owner_id", "category_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="归属用户ID")
    category_id: Mapped[int | None] = mapped_column(BigInteger, comment="所属分类ID（NULL=未分类全局兜底）")
    account_ids: Mapped[list | None] = mapped_column(JSON, comment="兜底下单账号ID列表（JSON数组，多选轮换使用）")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0", comment="是否已删除（软删除）")
