"""
个人发布地址库模型

功能：
1. 定义用户个人发布地址库表结构（xy_user_publish_addresses）
2. 每个用户独立维护自己的地址数据（owner_id 隔离）
3. 商品发布时优先随机使用该用户的个人地址
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class UserPublishAddress(TimestampMixin, Base):
    """个人发布地址库表"""

    __tablename__ = "xy_user_publish_addresses"
    __table_args__ = (
        Index("idx_upa_owner_deleted", "owner_id", "is_deleted"),
        Index("idx_upa_owner_addr", "owner_id", "address"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="归属用户ID")
    address: Mapped[str] = mapped_column(String(200), nullable=False, comment="地址文本（去重键）")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0", comment="是否已删除（软删除）")
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="使用次数")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最后使用时间")
