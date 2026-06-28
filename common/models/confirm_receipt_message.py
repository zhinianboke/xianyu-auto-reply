"""确认收货消息模型

用于存储账号确认收货后发送给买家的消息配置
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class ConfirmReceiptMessage(Base):
    """确认收货消息设置表"""

    __tablename__ = "xy_confirm_receipt_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True, comment="账号ID")  # 账号ID，一个账号只有一条配置
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否启用")  # 是否启用
    message_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="消息文本内容")  # 消息文本内容
    message_image: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="消息图片URL")  # 消息图片URL
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

