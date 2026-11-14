from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.message_notification import MessageNotification
from common.models.notification_channel import NotificationChannel
from common.models.data_dictionary import XYDataDictionary
from common.models.xy_account import XYAccount
from common.schemas.notification import (
    MessageNotificationSet,
)
from common.services.notification_types import (
    DEFAULT_NOTIFICATION_TYPES,
    NOTIFICATION_TYPE_DICTIONARY,
    NotificationTypeValueError,
    normalize_notification_types,
    resolve_stored_notification_types,
)
from app.services.account_service import AccountService
# 保留原服务导出路径，兼容现有路由和依赖注入。
from app.services.notification_channel_service import (
    NotificationChannelService,
    NotificationConfigValidationError,
    NotificationTemplateValidationError,
    NotificationTypeValidationError,
)


class MessageNotificationService:
    """Account notification subscriptions."""

    DEFAULT_NOTIFY_TYPES = ",".join(DEFAULT_NOTIFICATION_TYPES)

    def __init__(self, session: AsyncSession):
        self.session = session
        self.account_service = AccountService(session)

    @classmethod
    def normalize_notify_types(cls, value) -> str:
        """严格校验入参并归一化成逗号分隔串。

        Args:
            value: 客户端显式提交的通知类型列表。
        Returns:
            按公共固定顺序排列的逗号分隔值。
        Raises:
            NotificationTypeValidationError: 类型为空或包含未知值。
        """
        if value is None:
            return cls.DEFAULT_NOTIFY_TYPES
        try:
            return ",".join(normalize_notification_types(value))
        except NotificationTypeValueError as error:
            raise NotificationTypeValidationError(str(error)) from error

    async def get_notify_type_options(self) -> list[dict[str, str]]:
        """从数据字典读取通知事件类型及中文名称。"""
        result = await self.session.execute(
            select(XYDataDictionary)
            .where(
                XYDataDictionary.dict_type == NOTIFICATION_TYPE_DICTIONARY,
                XYDataDictionary.enabled.is_(True),
                XYDataDictionary.dict_value.in_(DEFAULT_NOTIFICATION_TYPES),
            )
            .order_by(XYDataDictionary.sort_order.asc(), XYDataDictionary.id.asc())
        )
        return [
            {"value": item.dict_value, "label": item.dict_label}
            for item in result.scalars().all()
        ]

    async def list_notifications(self, owner_id: int) -> dict[str, list[dict[str, Any]]]:
        rows = await self._query_notifications(owner_id)
        return self._aggregate(rows)

    async def list_notification_page(
        self,
        owner_id: int,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """分页查询当前用户的消息通知绑定。

        Args:
            owner_id: 当前用户ID。
            page: 页码，从1开始。
            page_size: 每页条数。
        Returns:
            包含列表、总数和页码信息的分页数据。
        """
        base_stmt = (
            select(MessageNotification, NotificationChannel, XYAccount.account_id)
            .join(NotificationChannel, NotificationChannel.id == MessageNotification.channel_id)
            .join(XYAccount, XYAccount.id == MessageNotification.account_pk)
            .where(
                MessageNotification.owner_id == owner_id,
                MessageNotification.is_deleted.is_(False),
                NotificationChannel.is_deleted.is_(False),
                NotificationChannel.owner_id == owner_id,
                XYAccount.owner_id == owner_id,
            )
        )
        total_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = int((await self.session.execute(total_stmt)).scalar_one())
        pages = max(1, (total + page_size - 1) // page_size)
        actual_page = min(page, pages)
        rows = (
            await self.session.execute(
                base_stmt.order_by(XYAccount.account_id, MessageNotification.id)
                .offset((actual_page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        items = [self._serialize_notification(*row) for row in rows]
        return {
            "items": items,
            "total": total,
            "page": actual_page,
            "page_size": page_size,
            "pages": pages,
        }

    async def list_for_account(self, owner_id: int, account_identifier: str) -> list[dict[str, Any]]:
        account = await self.account_service.get_account_for_user(owner_id, account_identifier)
        if not account:
            return []
        rows = await self._query_notifications(owner_id, account.account_id)
        grouped = self._aggregate(rows)
        return grouped.get(account.account_id, [])

    async def set_notification(
        self,
        owner_id: int,
        account_identifier: str,
        payload: MessageNotificationSet,
    ) -> bool:
        notify_types = self.normalize_notify_types(payload.notify_types)
        account = await self.account_service.get_account_for_user(owner_id, account_identifier)
        if not account:
            return False
        # 同一账号串行写入；锁定读可看到等待期间提交的绑定，无需中途提交事务。
        account = (await self.session.execute(
            select(XYAccount)
            .where(XYAccount.id == account.id, XYAccount.owner_id == owner_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )).scalars().first()
        if not account:
            return False
        channel = await self._get_channel(owner_id, payload.channel_id)
        if not channel:
            return False

        stmt = (
            select(MessageNotification)
            .where(
                MessageNotification.owner_id == owner_id,
                MessageNotification.account_pk == account.id,
                MessageNotification.channel_id == channel.id,
            )
            .order_by(
                MessageNotification.is_deleted.asc(),
                MessageNotification.enabled.desc(),
                MessageNotification.id.desc(),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        subscriptions = list(result.scalars().all())
        active_subscriptions = [item for item in subscriptions if not item.is_deleted]
        subscription = (
            active_subscriptions[0]
            if active_subscriptions
            else max(subscriptions, key=lambda item: item.id, default=None)
        )
        if payload.notification_id is not None:
            subscription = next(
                (item for item in active_subscriptions if item.id == payload.notification_id), None
            )
            if subscription is None:
                return False

        if subscription:
            was_deleted = subscription.is_deleted
            subscription.enabled = bool(payload.enabled)
            subscription.is_deleted = False
            subscription.account_identifier = account.account_id
            # 只有显式传了才改：旧客户端只切启用/禁用时不会把已有订阅重置成全开
            # 软删除后重新添加等同新建；旧客户端不传时仍恢复为默认全类型。
            if payload.notify_types is not None or was_deleted:
                subscription.notify_types = notify_types
        else:
            subscription = MessageNotification(
                owner_id=owner_id,
                account_pk=account.id,
                account_identifier=account.account_id,
                channel_id=channel.id,
                enabled=bool(payload.enabled),
                notify_types=notify_types,
            )

        self.session.add(subscription)
        await self.session.commit()
        return True

    async def update_subscription_enabled(
        self,
        owner_id: int,
        notification_id: int,
        enabled: bool,
    ) -> bool:
        """按绑定ID更新启停状态，兼容已有移动端调用。

        Args:
            owner_id: 当前用户ID。
            notification_id: 消息通知绑定ID。
            enabled: 是否启用该绑定。
        Returns:
            找到并更新返回True，否则返回False。
        """
        stmt = select(MessageNotification).where(
            MessageNotification.owner_id == owner_id,
            MessageNotification.id == notification_id,
            MessageNotification.is_deleted.is_(False),
        )
        subscription = (await self.session.execute(
            stmt.with_for_update().execution_options(populate_existing=True)
        )).scalars().first()
        if not subscription:
            return False
        subscription.enabled = bool(enabled)
        self.session.add(subscription)
        await self.session.commit()
        return True

    async def delete_subscription(self, owner_id: int, notification_id: int) -> bool:
        stmt = select(MessageNotification).where(
            MessageNotification.owner_id == owner_id,
            MessageNotification.id == notification_id,
            MessageNotification.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt.with_for_update().execution_options(populate_existing=True))
        subscription = result.scalars().first()
        if not subscription:
            return False
        subscription.is_deleted = True
        subscription.enabled = False
        self.session.add(subscription)
        await self.session.commit()
        return True

    async def delete_for_account(self, owner_id: int, account_identifier: str) -> bool:
        account = await self.account_service.get_account_for_user(owner_id, account_identifier)
        if not account:
            return False
        # 与添加绑定共用账号行锁，避免删除账号绑定时漏掉同时创建的记录。
        account_pk = await self.session.scalar(
            select(XYAccount.id).where(XYAccount.id == account.id, XYAccount.owner_id == owner_id).with_for_update()
        )
        if account_pk is None:
            return False
        stmt = select(MessageNotification).where(
            MessageNotification.owner_id == owner_id,
            MessageNotification.account_pk == account.id,
            MessageNotification.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt.with_for_update().execution_options(populate_existing=True))
        subscriptions = result.scalars().all()
        if not subscriptions:
            return False
        for sub in subscriptions:
            sub.is_deleted = True
            sub.enabled = False
            self.session.add(sub)
        await self.session.commit()
        return True

    async def _get_channel(self, owner_id: int, channel_id: int) -> NotificationChannel | None:
        stmt = select(NotificationChannel).where(
            NotificationChannel.owner_id == owner_id,
            NotificationChannel.id == channel_id,
            NotificationChannel.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt.with_for_update())
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
                MessageNotification.is_deleted.is_(False),
                NotificationChannel.enabled.is_(True),
                NotificationChannel.is_deleted.is_(False),
                NotificationChannel.owner_id == owner_id,
                XYAccount.owner_id == owner_id,
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
            item = self._serialize_notification(subscription, channel, account_id)
            item.pop("cookie_id")
            aggregated.setdefault(account_id, []).append(item)
        return aggregated

    @staticmethod
    def _serialize_notification(
        subscription: MessageNotification,
        channel: NotificationChannel,
        account_id: str,
    ) -> dict[str, Any]:
        """序列化单条消息通知绑定，并兼容历史通知类型值。"""
        notify_types, _ = resolve_stored_notification_types(subscription.notify_types)
        return {
            "id": subscription.id,
            "cookie_id": account_id,
            "channel_id": channel.id,
            # enabled 保持旧接口的“最终是否生效”语义；新增字段用于管理端区分两级开关。
            "enabled": subscription.enabled and channel.enabled,
            "subscription_enabled": subscription.enabled,
            "channel_enabled": channel.enabled,
            "channel_name": channel.name,
            "channel_type": channel.channel_type,
            "channel_config": channel.config_payload or {},
            "notify_types": list(notify_types),
        }
