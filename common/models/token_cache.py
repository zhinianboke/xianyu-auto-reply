"""
Token缓存模型

功能：
1. 存储IM Token和Device ID的缓存
2. 支持按user_id查询和更新
3. 记录过期时间，替代Redis缓存
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class TokenCache(TimestampMixin, Base):
    """Token缓存表"""

    __tablename__ = "xy_token_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="用户ID（myid）")
    token: Mapped[str] = mapped_column(Text, nullable=False, comment="IM Token")
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="设备ID")
    expire_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="过期时间")
