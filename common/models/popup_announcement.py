"""
弹窗公告模型

功能：
1. 定义弹窗公告表结构（xy_popup_announcements）
2. 支持公告标题、内容、跳转链接
3. 支持启用/停用开关（is_enabled）
4. 支持软删除（is_deleted）
5. 仅管理员可操作，用户每次登录时弹窗展示
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class PopupAnnouncement(Base):
    """弹窗公告表"""
    __tablename__ = "xy_popup_announcements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="弹窗公告ID")
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="公告标题")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="公告内容")
    link: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="跳转链接")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
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
