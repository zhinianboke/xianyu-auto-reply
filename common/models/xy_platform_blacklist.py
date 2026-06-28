"""
闲鱼黑名单模型

功能：
1. 定义闲鱼平台黑名单表结构（xy_platform_blacklist）
2. 存储从闲鱼平台同步的黑名单数据
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class XYPlatformBlacklist(TimestampMixin, Base):
    """闲鱼黑名单表"""

    __tablename__ = "xy_platform_blacklist"
    __table_args__ = (
        Index("idx_plb_owner_buyer", "owner_id", "buyer_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="拉黑用户（本系统用户ID）")
    buyer_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="买家ID")
    buyer_nick: Mapped[str | None] = mapped_column(String(120), nullable=True, comment="买家昵称")
