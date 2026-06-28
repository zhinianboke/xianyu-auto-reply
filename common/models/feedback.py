"""
意见反馈模型

功能：
1. 定义意见反馈表结构（xy_feedbacks）
2. 反馈类型枚举（FEATURE/BUG/OTHER）
3. 支持图片上传、解决状态
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class FeedbackType(str, enum.Enum):
    """反馈类型"""
    FEATURE = "FEATURE"  # 需求
    BUG = "BUG"          # BUG
    OTHER = "OTHER"      # 其他


class Feedback(TimestampMixin, Base):
    """意见反馈表"""
    __tablename__ = "xy_feedbacks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="反馈ID")
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="用户ID")
    cookie_id: Mapped[str | None] = mapped_column(String(64), comment="关联账号ID")
    title: Mapped[str] = mapped_column(String(100), comment="标题")
    content: Mapped[str] = mapped_column(Text, comment="内容（第一条消息）")
    feedback_type: Mapped[FeedbackType] = mapped_column(
        Enum(FeedbackType),
        default=FeedbackType.OTHER,
        comment="反馈类型"
    )
    images: Mapped[str | None] = mapped_column(Text, comment="图片URL，JSON数组")
    is_resolved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        comment="是否已解决"
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="解决时间"
    )
    admin_reply: Mapped[str | None] = mapped_column(Text, comment="管理员回复（兼容旧数据）")

