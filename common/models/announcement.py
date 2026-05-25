"""
公告信息模型

功能：
1. 定义公告信息表结构（xy_announcements）
2. 支持公告标题、内容、创建时间
3. 支持软删除
4. 仅管理员可操作
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class Announcement(Base):
    """公告信息表"""
    __tablename__ = "xy_announcements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="公告ID")
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="公告标题")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="公告内容")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否已删除")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )

