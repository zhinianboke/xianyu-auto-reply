"""
个人黑名单模型

功能：
1. 定义个人黑名单表结构（xy_personal_blacklist）
2. 存储用户自定义的买家黑名单
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class XYPersonalBlacklist(TimestampMixin, Base):
    """个人黑名单表"""

    __tablename__ = "xy_personal_blacklist"
    __table_args__ = (
        Index("idx_pb_owner_buyer", "owner_id", "buyer_id"),
        Index("idx_pb_owner_account", "owner_id", "account_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="用户ID")
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="账号ID")
    buyer_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="买家ID")
    buyer_nick: Mapped[str | None] = mapped_column(String(120), nullable=True, comment="买家昵称")
    item_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="商品ID")
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="拉黑原因")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否启用")
