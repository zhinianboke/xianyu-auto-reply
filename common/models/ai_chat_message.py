"""
AI聊天消息模型

存储AI对话的消息记录，用于上下文管理和议价次数统计
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class AIChatMessage(Base):
    """AI聊天消息表
    
    存储每条对话消息，包括用户消息和AI回复
    用于：
    - 对话上下文管理
    - 议价次数统计
    - 消息去重
    """
    
    __tablename__ = "xy_ai_chat_messages"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cookie_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    item_id: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(20))  # price / tech / default
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    __table_args__ = (
        Index("ix_ai_chat_messages_chat_cookie", "chat_id", "cookie_id"),
        Index("ix_ai_chat_messages_intent", "cookie_id", "intent"),
    )

