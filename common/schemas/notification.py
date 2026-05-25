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
    channel_id: int
    enabled: bool = True

