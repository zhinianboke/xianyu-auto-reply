"""商品售罄自动续售任务，由后端服务执行。"""
from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import and_, or_, select, text

from common.db.session import async_session_maker
from common.models.auto_relist_event import AutoRelistEvent
from common.models.auto_relist_rule import AutoRelistRule
from common.models.product_material import ProductMaterial
from common.models.xy_account import XYAccount
from common.models.xy_order import XYOrder
from common.services.item_service import ItemService
from common.services.publish_execution_service import execute_single_publish
from common.utils.time_utils import get_beijing_now_naive


def _material_to_publish_data(material: ProductMaterial) -> dict[str, Any]:
    """把持久化素材还原为公共发布服务需要的参数。"""
    return {
        "id": material.id,
        "title": material.title,
        "description": material.description,
        "price": float(material.price or 0),
        "original_price": float(material.original_price) if material.original_price is not None else None,
        "category": material.category,
        "platform_category_id": material.platform_category_id,
        "platform_category_name": material.platform_category_name,
        "platform_channel_category_id": material.platform_channel_category_id,
        "platform_channel_category_name": material.platform_channel_category_name,
        "platform_leaf_id": material.platform_leaf_id,
        "platform_tb_category_id": material.platform_tb_category_id,
        "platform_category_path": material.platform_category_path or [],
        "platform_attributes": material.platform_attributes or [],
        "category_source": material.category_source or "manual",
        "category_confidence": (
            float(material.category_confidence) if material.category_confidence is not None else None
        ),
        "images": material.images or [],
        "videos": material.videos or [],
        "specifications": material.specifications or [],
        "sku_rows": material.sku_rows or [],
        "quantity": material.quantity or 1,
        "delivery_method": material.delivery_method,
        "shipping_method": material.shipping_method or ("fixed" if material.postage else "free"),
        "support_pickup": bool(material.support_pickup),
        "postage": float(material.postage or 0),
        "address": material.address,
        "address_expected_text": material.address_expected_text,
        "brand": material.brand,
        "condition": material.condition,
        "remark": material.remark,
    }


class AutoRelistTask:
    """发现已售罄商品并用原素材重新发布。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def execute(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            await self._recover_stale_events()
            await self._discover_events()
            await self._process_due_events()

    async def _recover_stale_events(self) -> None:
        now = get_beijing_now_naive()
        async with async_session_maker() as session:
            events = (
                await session.execute(
                    select(AutoRelistEvent).where(
                        AutoRelistEvent.status == "publishing",
                        AutoRelistEvent.updated_at < now - timedelta(minutes=10),
                    )
                )
            ).scalars().all()
            for event in events:
                event.status = "retry"
                event.next_retry_at = now
                event.error_message = "上次执行中断，已自动恢复"
            if events:
                await session.commit()

    async def _discover_events(self) -> None:
        now = get_beijing_now_naive()
        async with async_session_maker() as session:
            rules = (
                await session.execute(select(AutoRelistRule).where(AutoRelistRule.enabled.is_(True)))
            ).scalars().all()

            for rule in rules:
                order = (
                    await session.execute(
                        select(XYOrder)
                        .where(
                            XYOrder.owner_id == rule.user_id,
                            XYOrder.account_id == rule.account_id,
                            XYOrder.item_id == rule.current_item_id,
                            XYOrder.status.in_(["shipped", "completed"]),
                            XYOrder.delivery_method == "auto",
                            XYOrder.delivery_content.is_not(None),
                            XYOrder.delivery_content != "",
                            or_(rule.last_order_no is None, XYOrder.order_no != rule.last_order_no),
                        )
                        .order_by(XYOrder.updated_at.desc(), XYOrder.id.desc())
                        .limit(1)
                    )
                ).scalars().first()
                if not order:
                    continue

                exists = (
                    await session.execute(
                        select(AutoRelistEvent.id).where(
                            AutoRelistEvent.rule_id == rule.id,
                            AutoRelistEvent.order_no == order.order_no,
                        )
                    )
                ).scalar_one_or_none()
                if exists:
                    continue

                order_updated_at = order.updated_at
                if order_updated_at and order_updated_at.tzinfo:
                    order_updated_at = order_updated_at.replace(tzinfo=None)
                due_at = max(now, (order_updated_at or now) + timedelta(seconds=rule.delay_seconds))
                session.add(
                    AutoRelistEvent(
                        user_id=rule.user_id,
                        rule_id=rule.id,
                        material_id=rule.material_id,
                        account_id=rule.account_id,
                        order_no=order.order_no,
                        old_item_id=rule.current_item_id,
                        status="pending",
                        next_retry_at=due_at,
                    )
                )
                rule.status = "waiting"
                rule.next_retry_at = due_at
            await session.commit()

    async def _process_due_events(self) -> None:
        now = get_beijing_now_naive()
        async with async_session_maker() as session:
            event_ids = (
                await session.execute(
                    select(AutoRelistEvent.id)
                    .where(
                        AutoRelistEvent.status.in_(["pending", "retry"]),
                        or_(
                            AutoRelistEvent.next_retry_at.is_(None),
                            AutoRelistEvent.next_retry_at <= now,
                        ),
                    )
                    .order_by(AutoRelistEvent.created_at)
                    .limit(10)
                )
            ).scalars().all()

        for event_id in event_ids:
            await self._process_event(int(event_id))

    async def _process_event(self, event_id: int) -> None:
        now = get_beijing_now_naive()
        async with async_session_maker() as session:
            event = await session.get(AutoRelistEvent, event_id)
            if not event or event.status not in {"pending", "retry"}:
                return
            rule = await session.get(AutoRelistRule, event.rule_id)
            if not rule or not rule.enabled:
                event.status = "skipped"
                event.error_message = "自动续售已关闭"
                await session.commit()
                return
            if rule.current_item_id != event.old_item_id:
                event.status = "skipped"
                event.error_message = "规则已绑定到更新的商品"
                await session.commit()
                return

            material = await session.get(ProductMaterial, event.material_id)
            account = (
                await session.execute(
                    select(XYAccount).where(
                        XYAccount.owner_id == event.user_id,
                        XYAccount.account_id == event.account_id,
                    )
                )
            ).scalars().first()
            if not material or material.is_deleted or not account:
                await self._record_failure(session, event, rule, "素材或闲鱼账号不存在")
                return

            event.status = "publishing"
            event.attempt_count += 1
            event.error_message = None
            await session.commit()

            fetch_result = await ItemService(session).fetch_all_items_from_account(
                account=account,
                stop_when_page_all_existing=False,
            )
            if fetch_result.get("skipped"):
                event.attempt_count = max(0, event.attempt_count - 1)
                event.status = "retry"
                event.next_retry_at = now + timedelta(seconds=60)
                rule.status = "waiting"
                rule.next_retry_at = event.next_retry_at
                await session.commit()
                return
            if not fetch_result.get("success"):
                await self._record_failure(
                    session,
                    event,
                    rule,
                    f"确认商品状态失败：{fetch_result.get('message') or '未知错误'}",
                )
                return

            live_item_ids = {
                str(item.get("id") or "").strip() for item in fetch_result.get("items") or []
            }
            if event.old_item_id in live_item_ids:
                event.attempt_count = max(0, event.attempt_count - 1)
                event.status = "pending"
                event.next_retry_at = now + timedelta(seconds=60)
                rule.status = "waiting"
                rule.next_retry_at = event.next_retry_at
                await session.commit()
                return

            result = await execute_single_publish(
                session=session,
                user_id=event.user_id,
                account_id=event.account_id,
                item_data=_material_to_publish_data(material),
                static_root=Path(os.environ.get("STATIC_DIR", "static")),
            )
            new_item_id = str(result.get("item_id") or "").strip()
            if not result.get("success") or not new_item_id:
                await self._record_failure(
                    session,
                    event,
                    rule,
                    f"重新发布失败：{result.get('message') or '未返回新商品ID'}",
                )
                return

            await session.execute(
                text(
                    """
                    INSERT IGNORE INTO xy_card_item_relations
                        (user_id, card_id, item_id, source, dock_record_id, created_at, updated_at)
                    VALUES (:user_id, :card_id, :item_id, 'own', 0, NOW(), NOW())
                    """
                ),
                {"user_id": event.user_id, "card_id": rule.card_id, "item_id": new_item_id},
            )
            event.status = "success"
            event.new_item_id = new_item_id
            event.next_retry_at = None
            event.error_message = None
            rule.current_item_id = new_item_id
            rule.last_order_no = event.order_no
            rule.last_old_item_id = event.old_item_id
            rule.last_new_item_id = new_item_id
            rule.last_relisted_at = now
            rule.status = "active"
            rule.retry_count = 0
            rule.next_retry_at = None
            rule.last_error = None
            await session.commit()
            logger.info(
                "[自动续售] 素材{}已从商品{}续售为{}",
                event.material_id,
                event.old_item_id,
                new_item_id,
            )

    async def _record_failure(
        self,
        session,
        event: AutoRelistEvent,
        rule: AutoRelistRule,
        message: str,
    ) -> None:
        retry_delays = (60, 300, 900)
        now = get_beijing_now_naive()
        attempt = max(1, int(event.attempt_count or 0))
        event.error_message = message[:2000]
        rule.retry_count = attempt
        rule.last_error = message[:2000]
        if attempt >= len(retry_delays):
            event.status = "failed"
            event.next_retry_at = None
            rule.status = "error"
            rule.next_retry_at = None
        else:
            event.status = "retry"
            event.next_retry_at = now + timedelta(seconds=retry_delays[attempt - 1])
            rule.status = "retrying"
            rule.next_retry_at = event.next_retry_at
        await session.commit()
        logger.warning("[自动续售] 素材{}执行失败：{}", event.material_id, message)


auto_relist_task_service = AutoRelistTask()
