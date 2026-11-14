from __future__ import annotations

from pydantic import BaseModel


class NotificationChannelBase(BaseModel):
    name: str
    type: str
    config: str | dict | None = None
    enabled: bool = True


class NotificationChannelCreate(NotificationChannelBase):
    """Create payload for notification channels."""


class NotificationChannelUpdate(BaseModel):
    """Partial update payload for notification channels."""

    name: str | None = None
    type: str | None = None
    config: str | dict | None = None
    enabled: bool | None = None


class MessageNotificationSet(BaseModel):
    # 网页按ID编辑，避免历史重复绑定时误改另一条；旧客户端可省略。
    notification_id: int | None = None
    channel_id: int
    enabled: bool = True
    # 订阅事件类型；缺省时新建全开、更新保留已有范围，兼容旧客户端。
    notify_types: list[str] | None = None


class MessageNotificationToggle(BaseModel):
    """按绑定ID更新启停状态的兼容请求。"""

    enabled: bool

