"""
消息通知模型

功能：
1. 定义消息通知表结构（xy_message_notifications）
2. 关联账号和通知渠道
3. 控制账号的通知订阅状态
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base_class import Base, TimestampMixin


class MessageNotification(TimestampMixin, Base):
    """消息通知表 - 关联账号和通知渠道"""

    __tablename__ = "xy_message_notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    account_pk: Mapped[int] = mapped_column(BigInteger, index=True)
    account_identifier: Mapped[str] = mapped_column(String(80), nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    channel: Mapped["NotificationChannel"] = relationship(
        "NotificationChannel",
        primaryjoin="MessageNotification.channel_id == NotificationChannel.id",
        foreign_keys="[MessageNotification.channel_id]",
        back_populates="subscriptions",
        viewonly=True,
    )

