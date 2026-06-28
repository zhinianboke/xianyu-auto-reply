"""
商品发布随机地址池模型

功能：
1. 定义商品发布随机地址池表结构（xy_publish_addresses）
2. 支持全局通用地址和账号专用地址
3. 为商品发布提供可维护的随机地址来源
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class PublishAddress(TimestampMixin, Base):
    """商品发布随机地址池表"""

    __tablename__ = "xy_publish_addresses"
    __table_args__ = (
        Index("idx_pa_enabled_account", "is_enabled", "account_id"),
        Index("idx_pa_sort_created", "sort_order", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="地址名称")
    search_keyword: Mapped[str] = mapped_column(String(200), nullable=False, comment="地址搜索关键词")
    expected_text: Mapped[str | None] = mapped_column(String(200), comment="期望命中的候选文本")
    account_id: Mapped[str | None] = mapped_column(String(80), index=True, comment="限定使用的闲鱼账号ID，空表示全局通用")
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1", comment="随机权重")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100", comment="排序值")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1", comment="是否启用")
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="使用次数")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最后使用时间")
    created_by: Mapped[int | None] = mapped_column(BigInteger, comment="创建人用户ID")
    remark: Mapped[str | None] = mapped_column(String(500), comment="备注")
