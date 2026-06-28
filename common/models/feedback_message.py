"""
意见反馈消息模型

功能：
1. 定义反馈消息表结构（xy_feedback_messages）
2. 支持用户和管理员多次对话
3. 按时间升序显示对话内容
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class FeedbackMessage(TimestampMixin, Base):
    """反馈消息表（对话记录）"""
    __tablename__ = "xy_feedback_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="消息ID")
    feedback_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="关联反馈ID")
    user_id: Mapped[int] = mapped_column(BigInteger, comment="发送者用户ID")
    content: Mapped[str] = mapped_column(Text, comment="消息内容")
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        comment="是否为管理员消息"
    )
