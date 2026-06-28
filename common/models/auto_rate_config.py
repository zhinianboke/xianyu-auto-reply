"""
自动评价配置模型

功能：
1. 存储账号的自动评价配置
2. 支持固定文字和API两种评价内容来源
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class AutoRateConfig(TimestampMixin, Base):
    """自动评价配置表"""

    __tablename__ = "xy_auto_rate_configs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, comment="账号ID")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否启用自动评价")
    rate_type: Mapped[str] = mapped_column(String(20), default="text", comment="评价类型: text-固定文字, api-API获取")
    text_content: Mapped[str | None] = mapped_column(Text, comment="固定评价文字内容")
    api_url: Mapped[str | None] = mapped_column(String(512), comment="API地址")

