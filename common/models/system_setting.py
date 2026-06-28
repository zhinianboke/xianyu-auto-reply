"""
系统设置模型

功能：
1. 定义系统设置表结构（xy_system_settings）
2. 存储全局键值对配置
3. 支持设置描述和更新时间
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class SystemSetting(Base):
    """系统设置表 - 存储全局键值对配置"""

    __tablename__ = "xy_system_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True, comment="设置键")
    value: Mapped[str] = mapped_column(Text, nullable=False, comment="设置值")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="设置描述")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )

