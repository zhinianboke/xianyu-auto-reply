"""
通知渠道模型

功能：
1. 定义通知渠道表结构（xy_notification_channels）
2. 支持多种通知类型（钉钉、微信、邮件等）
3. 存储渠道配置信息
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base_class import Base, TimestampMixin


class NotificationChannel(TimestampMixin, Base):
    """通知渠道表 - 配置消息通知渠道"""

    __tablename__ = "xy_notification_channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="渠道ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="所属用户ID")
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="渠道名称")
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="渠道类型")
    config_payload: Mapped[dict | None] = mapped_column("config", JSON, comment="渠道配置")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")

    subscriptions: Mapped[list["MessageNotification"]] = relationship(
        "MessageNotification",
        primaryjoin="NotificationChannel.id == MessageNotification.channel_id",
        foreign_keys="MessageNotification.channel_id",
        back_populates="channel",
        viewonly=True,
    )

