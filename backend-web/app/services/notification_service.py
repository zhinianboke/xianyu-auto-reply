from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.message_notification import MessageNotification
from common.models.notification_channel import NotificationChannel
from common.models.xy_account import XYAccount
from common.schemas.notification import (
    MessageNotificationSet,
    NotificationChannelCreate,
    NotificationChannelUpdate,
)
from app.services.account_service import AccountService


class NotificationChannelService:
    """Manage notification channels for a user."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_channels(self, owner_id: int) -> list[dict[str, Any]]:
        stmt = (
            select(NotificationChannel)
            .where(NotificationChannel.owner_id == owner_id)
            .order_by(NotificationChannel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._serialize(channel) for channel in result.scalars().all()]

    async def create_channel(
        self,
        owner_id: int,
        payload: NotificationChannelCreate,
    ) -> dict[str, Any]:
        config = self._parse_config(payload.config)
        channel = NotificationChannel(
            owner_id=owner_id,
            name=payload.name.strip(),
            channel_type=payload.type.strip(),
            config_payload=config,
            enabled=bool(payload.enabled),
        )
        self.session.add(channel)
        await self.session.commit()
        await self.session.refresh(channel)
        return self._serialize(channel)

    async def get_channel(self, owner_id: int, channel_id: int) -> NotificationChannel | None:
        stmt = select(NotificationChannel).where(
            NotificationChannel.owner_id == owner_id,
            NotificationChannel.id == channel_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def update_channel(
        self,
        owner_id: int,
        channel_id: int,
        payload: NotificationChannelUpdate,
    ) -> dict[str, Any] | None:
        channel = await self.get_channel(owner_id, channel_id)
        if not channel:
            return None

        if payload.name is not None:
            channel.name = payload.name.strip()
        if payload.type is not None:
            channel.channel_type = payload.type.strip()
        if payload.config is not None:
            channel.config_payload = self._parse_config(payload.config)
        if payload.enabled is not None:
            channel.enabled = bool(payload.enabled)

        self.session.add(channel)
        await self.session.commit()
        await self.session.refresh(channel)
        return self._serialize(channel)

    async def delete_channel(self, owner_id: int, channel_id: int) -> bool:
        channel = await self.get_channel(owner_id, channel_id)
        if not channel:
            return False
        await self.session.delete(channel)
        await self.session.commit()
        return True

    def _serialize(self, channel: NotificationChannel) -> dict[str, Any]:
        return {
            "id": channel.id,
            "name": channel.name,
            "type": channel.channel_type,
            "config": channel.config_payload or {},
            "enabled": channel.enabled,
            "created_at": channel.created_at,
            "updated_at": channel.updated_at,
        }

    def _parse_config(self, config: str | dict | None) -> dict | None:
        if config is None:
            return None
        if isinstance(config, dict):
            return config
        value = config.strip()
        if not value:
            return None
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"raw": value}


class MessageNotificationService:
    """Account notification subscriptions."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.account_service = AccountService(session)

    async def list_notifications(self, owner_id: int) -> dict[str, list[dict[str, Any]]]:
        rows = await self._query_notifications(owner_id)
        return self._aggregate(rows)

    async def list_for_account(self, owner_id: int, account_identifier: str) -> list[dict[str, Any]]:
        rows = await self._query_notifications(owner_id, account_identifier)
        grouped = self._aggregate(rows)
        return grouped.get(account_identifier, [])

    async def set_notification(
        self,
        owner_id: int,
        account_identifier: str,
        payload: MessageNotificationSet,
    ) -> bool:
        account = await self.account_service.get_account_for_user(owner_id, account_identifier)
        if not account:
            return False
        channel = await self._get_channel(owner_id, payload.channel_id)
        if not channel:
            return False

        stmt = select(MessageNotification).where(
            MessageNotification.owner_id == owner_id,
            MessageNotification.account_pk == account.id,
            MessageNotification.channel_id == channel.id,
        )
        result = await self.session.execute(stmt)
        subscription = result.scalars().first()

        if subscription:
            subscription.enabled = bool(payload.enabled)
            subscription.account_identifier = account.account_id
        else:
            subscription = MessageNotification(
                owner_id=owner_id,
                account_pk=account.id,
                account_identifier=account.account_id,
                channel_id=channel.id,
                enabled=bool(payload.enabled),
            )

        self.session.add(subscription)
        await self.session.commit()
        return True

    async def delete_subscription(self, owner_id: int, notification_id: int) -> bool:
        stmt = select(MessageNotification).where(
            MessageNotification.owner_id == owner_id,
            MessageNotification.id == notification_id,
        )
        result = await self.session.execute(stmt)
        subscription = result.scalars().first()
        if not subscription:
            return False
        await self.session.delete(subscription)
        await self.session.commit()
        return True

    async def delete_for_account(self, owner_id: int, account_identifier: str) -> bool:
        account = await self.account_service.get_account_for_user(owner_id, account_identifier)
        if not account:
            return False
        stmt = select(MessageNotification).where(
            MessageNotification.owner_id == owner_id,
            MessageNotification.account_pk == account.id,
        )
        result = await self.session.execute(stmt)
        subscriptions = result.scalars().all()
        if not subscriptions:
            return False
        for sub in subscriptions:
            await self.session.delete(sub)
        await self.session.commit()
        return True

    async def _get_channel(self, owner_id: int, channel_id: int) -> NotificationChannel | None:
        stmt = select(NotificationChannel).where(
            NotificationChannel.owner_id == owner_id,
            NotificationChannel.id == channel_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _query_notifications(
        self,
        owner_id: int,
        account_identifier: str | None = None,
    ) -> list[tuple[MessageNotification, NotificationChannel, str]]:
        stmt = (
            select(MessageNotification, NotificationChannel, XYAccount.account_id)
            .join(NotificationChannel, NotificationChannel.id == MessageNotification.channel_id)
            .join(XYAccount, XYAccount.id == MessageNotification.account_pk)
            .where(
                MessageNotification.owner_id == owner_id,
                NotificationChannel.enabled.is_(True),
            )
            .order_by(XYAccount.account_id, MessageNotification.id)
        )
        if account_identifier:
            stmt = stmt.where(XYAccount.account_id == account_identifier)
        result = await self.session.execute(stmt)
        return result.all()

    def _aggregate(
        self,
        rows: list[tuple[MessageNotification, NotificationChannel, str]],
    ) -> dict[str, list[dict[str, Any]]]:
        aggregated: dict[str, list[dict[str, Any]]] = {}
        for subscription, channel, account_id in rows:
            aggregated.setdefault(account_id, []).append(
                {
                    "id": subscription.id,
                    "channel_id": channel.id,
                    "enabled": subscription.enabled and channel.enabled,
                    "channel_name": channel.name,
                    "channel_type": channel.channel_type,
                    "channel_config": channel.config_payload or {},
                }
            )
        return aggregated
