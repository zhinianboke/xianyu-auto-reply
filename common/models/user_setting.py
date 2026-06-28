"""用户设置模型"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class UserSetting(Base):
    """用户个人设置表"""

    __tablename__ = "xy_user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="设置ID")
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="用户ID")
    key: Mapped[str] = mapped_column(String(120), nullable=False, comment="设置键")
    value: Mapped[str] = mapped_column(Text, nullable=False, comment="设置值")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="设置描述")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )

    __table_args__ = (
        # 用户ID和key组合唯一
        {"mysql_charset": "utf8mb4"},
    )

