"""通知渠道的查询、配置校验与软删除服务。"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from common.models.notification_channel import NotificationChannel
from common.schemas.notification import NotificationChannelCreate, NotificationChannelUpdate
from common.utils.notification_template import validate_notification_templates
from common.utils.notification_config import parse_notification_config
from common.services.notification_types import (
    NotificationTypeValueError,
    normalize_notification_types,
    resolve_stored_notification_types,
)


class NotificationTemplateValidationError(ValueError):
    """Raised when a notification channel contains an invalid template."""


class NotificationTypeValidationError(ValueError):
    """通知事件类型配置不合法。"""


class NotificationConfigValidationError(ValueError):
    """通知渠道配置不是有效的JSON对象。"""


class NotificationChannelService:
    """Manage notification channels for a user."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_channels(self, owner_id: int) -> list[dict[str, Any]]:
        stmt = (
            select(NotificationChannel)
            .where(
                NotificationChannel.owner_id == owner_id,
                NotificationChannel.is_deleted.is_(False),
            )
            .order_by(NotificationChannel.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._serialize(channel) for channel in result.scalars().all()]

    async def list_channel_page(self, owner_id: int, page: int, page_size: int) -> dict[str, Any]:
        """按所属用户分页读取渠道，返回分页信息及各类型总数。"""
        filters = (NotificationChannel.owner_id == owner_id, NotificationChannel.is_deleted.is_(False))
        counts = (await self.session.execute(
            select(NotificationChannel.channel_type, func.count())
            .where(*filters).group_by(NotificationChannel.channel_type)
        )).all()
        total = sum(count for _, count in counts)
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        channels = (await self.session.execute(
            select(NotificationChannel).where(*filters)
            .order_by(NotificationChannel.created_at.desc(), NotificationChannel.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return {
            "items": [self._serialize(channel) for channel in channels],
            "total": total, "pages": pages, "page": page, "page_size": page_size,
            "type_counts": dict(counts),
        }

    async def create_channel(
        self,
        owner_id: int,
        payload: NotificationChannelCreate,
    ) -> dict[str, Any]:
        config = self._parse_config(payload.config)
        self._validate_template_config(config)
        self._validate_notify_types(config)
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

    async def get_channel(self, owner_id: int, channel_id: int, *, for_update: bool = False) -> NotificationChannel | None:
        stmt = select(NotificationChannel).where(
            NotificationChannel.owner_id == owner_id,
            NotificationChannel.id == channel_id,
            NotificationChannel.is_deleted.is_(False),
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def update_channel(
        self,
        owner_id: int,
        channel_id: int,
        payload: NotificationChannelUpdate,
    ) -> dict[str, Any] | None:
        channel = await self.get_channel(owner_id, channel_id, for_update=True)
        if not channel:
            return None

        config = None
        if payload.config is not None:
            config = self._parse_config(payload.config)
            # 旧客户端不提交新字段时，保留渠道已有的事件范围。
            if config is not None and "notify_types" not in config:
                try:
                    previous = parse_notification_config(channel.config_payload)
                except ValueError:
                    logger.warning("更新渠道时发现历史配置格式错误，以本次显式提交的配置修复：channel_id={}", channel_id)
                    previous = {}
                if "notify_types" in previous:
                    config["notify_types"] = list(resolve_stored_notification_types(previous["notify_types"])[0])
            self._validate_template_config(config)
            self._validate_notify_types(config)

        if payload.name is not None:
            channel.name = payload.name.strip()
        if payload.type is not None:
            channel.channel_type = payload.type.strip()
        if payload.config is not None:
            channel.config_payload = config
        if payload.enabled is not None:
            channel.enabled = bool(payload.enabled)

        self.session.add(channel)
        await self.session.commit()
        await self.session.refresh(channel)
        return self._serialize(channel)

    async def delete_channel(self, owner_id: int, channel_id: int) -> bool:
        channel = await self.get_channel(owner_id, channel_id, for_update=True)
        if not channel:
            return False
        channel.is_deleted = True
        channel.enabled = False
        self.session.add(channel)
        await self.session.commit()
        return True

    def _serialize(self, channel: NotificationChannel) -> dict[str, Any]:
        """返回可编辑的配置对象；有效旧字符串只在读取时解析，错误原文保留。"""
        try:
            config = parse_notification_config(channel.config_payload)
        except ValueError:
            logger.warning("通知渠道配置无法解析，返回原文供修复：channel_id={}", channel.id)
            config = channel.config_payload
        return {
            "id": channel.id,
            "name": channel.name,
            "type": channel.channel_type,
            "config": config,
            "enabled": channel.enabled,
            "created_at": channel.created_at,
            "updated_at": channel.updated_at,
        }

    def _parse_config(self, config: str | dict | None) -> dict | None:
        if config is None:
            return None
        if isinstance(config, dict):
            return dict(config)
        value = config.strip()
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            raise NotificationConfigValidationError("渠道配置必须为有效的JSON对象") from error
        if not isinstance(parsed, dict):
            raise NotificationConfigValidationError("渠道配置必须为JSON对象，不能为数组、空值或普通文本")
        return parsed

    def _validate_template_config(self, config: dict | None) -> None:
        """校验渠道配置中的模板字段，避免无效模板入库。

        Args:
            config: 解析后的通知渠道配置。
        Returns:
            校验成功时不返回内容；失败时抛出模板校验异常。
        """
        validation_error = validate_notification_templates(config)
        if validation_error:
            raise NotificationTemplateValidationError(validation_error)

    def _validate_notify_types(self, config: dict | None) -> None:
        """严格校验渠道级通知类型，新配置禁止写入未知值。

        Args:
            config: 解析后的通知渠道配置。
        Returns:
            校验成功时不返回内容。
        Raises:
            NotificationTypeValidationError: notify_types 格式错误、为空或包含未知值。
        """
        if not config or "notify_types" not in config:
            return
        try:
            config["notify_types"] = list(normalize_notification_types(config["notify_types"]))
        except NotificationTypeValueError as error:
            raise NotificationTypeValidationError(str(error)) from error

