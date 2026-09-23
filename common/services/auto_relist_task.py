"""商品成交后自动续售任务。"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, suppress
from datetime import timedelta
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select, update

from common.core.config import get_settings
from common.db.redis_client import distributed_lock
from common.db.session import async_session_maker
from common.models.auto_relist_event import AutoRelistEvent
from common.models.auto_relist_rule import AutoRelistRule
from common.models.card import Card
from common.models.card_item_relation import CardItemRelation
from common.models.product_material import ProductMaterial
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.models.xy_order import XYOrder
from common.services.item_service import ItemService
from common.services.publish_execution_service import execute_single_publish
from common.services.auto_relist_lifecycle import AutoRelistLifecycleMixin
from common.services.auto_relist_utils import (
    build_publish_request_id,
    material_to_publish_data,
    order_still_eligible,
)
from common.services.auto_relist_discovery import AutoRelistDiscoveryMixin
from common.services.relist_association_migration_service import RelistAssociationMigrationService
from common.utils.time_utils import get_beijing_now_naive
from common.utils.account_status import is_account_active

class AutoRelistTask(AutoRelistLifecycleMixin, AutoRelistDiscoveryMixin):
    """单例调度器调用的自动续售执行器。"""

    def __init__(
        self, lease_seconds: int = 900, batch_size: int = 10, max_retries: int = 3, static_dir: str = "static"
    ) -> None:
        self.lease_seconds = max(120, lease_seconds)
        self.batch_size = max(1, min(batch_size, 100))
        self.max_retries = max(1, min(max_retries, 20))
        self.static_dir = static_dir
        self._local_lock = asyncio.Lock()
    async def execute(self) -> None:
        """执行一次扫描，单个事件异常不会终止后续事件。"""
        if self._local_lock.locked():
            logger.warning("[自动续售] 本地锁被占用（后台循环或上一次触发仍在执行），本次跳过")
            return
        async with self._local_lock:
            async with AsyncExitStack() as stack:
                try:
                    runner_lock = await stack.enter_async_context(
                        distributed_lock("auto_relist:runner", expire=self.lease_seconds, blocking=False)
                    )
                except Exception as exc:
                    logger.warning("[自动续售] Redis 调度锁不可用，本次跳过并延迟重试: {}", exc)
                    await self._mark_runner_lock_unavailable()
                    return
                if not runner_lock.is_locked:
                    logger.warning("[自动续售] 调度锁被其他 worker 持有，本次跳过")
                    return
                runner_stop = asyncio.Event()
                runner_heartbeat = asyncio.create_task(
                    self._lock_heartbeat(runner_lock, runner_stop, "runner")
                )
                try:
                    await self._recover_expired_events()
                    await self._recover_legacy_manual_failed_events()
                    await self._discover_events()
                    event_ids = await self._list_due_events()
                    logger.info("[自动续售] 本轮到期事件数量: {}, event_ids={}", len(event_ids), event_ids)
                    for event_id in event_ids:
                        if runner_heartbeat.done():
                            logger.warning("[自动续售] runner 租约已失效，结束本轮扫描")
                            return
                        try:
                            await self._process_event(event_id)
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            logger.opt(exception=exc).error("[自动续售] 事件执行异常 event_id={}", event_id)
                finally:
                    runner_stop.set()
                    runner_heartbeat.cancel()
                    with suppress(asyncio.CancelledError):
                        await runner_heartbeat
    async def _process_event(self, event_id: int) -> None:
        token = await self._claim_event(event_id)
        if not token:
            logger.warning("[自动续售] 事件领取失败（状态非到期/被其他 worker 抢占）event_id={}", event_id)
            return
        logger.info("[自动续售] 已领取事件，开始处理 event_id={}", event_id)
        async with async_session_maker() as session:
            event = await session.get(AutoRelistEvent, event_id)
            if not event or event.status != "claimed" or event.claim_token != token:
                logger.warning("[自动续售] 事件领取后状态校验失败 event_id={}", event_id)
                return
            rule = await session.get(AutoRelistRule, event.rule_id)
            material = await session.get(ProductMaterial, event.material_id)
            account = (
                await session.execute(select(XYAccount).where(XYAccount.owner_id == event.user_id, XYAccount.account_id == event.account_id))
            ).scalars().first()
            card = None
            if rule:
                card = (
                    await session.execute(
                        select(Card).where(Card.id == rule.card_id, Card.user_id == event.user_id)
                    )
                ).scalars().first()
            if not rule or rule.user_id != event.user_id or rule.material_id != event.material_id:
                await self._skip_event(session, event, "自动续售规则不存在或归属不一致")
                return
            has_published_result = bool(event.publish_state == "succeeded" and event.publish_item_id)
            if not has_published_result:
                order = (
                    await session.execute(
                        select(XYOrder)
                        .where(
                            XYOrder.owner_id == event.user_id,
                            XYOrder.account_id == event.account_id,
                            XYOrder.order_no == event.order_no,
                            XYOrder.item_id == event.old_item_id,
                        )
                        .limit(1)
                    )
                ).scalars().first()
                if not order or not order_still_eligible(order):
                    await self._skip_event(session, event, "订单状态已变化（退款/取消或未完成发货），不再触发自动续售")
                    return
                if not rule.enabled:
                    await self._skip_event(session, event, "自动续售已关闭")
                    return
                if not material or material.user_id != event.user_id or material.is_deleted:
                    await self._pause_event(session, event, rule, "素材已移出素材库或归属不一致")
                    return
                if rule.account_id != event.account_id:
                    await self._skip_event(session, event, "规则账号配置已更新")
                    return
                if not account or not is_account_active(account.status) or not account.cookie:
                    await self._pause_event(session, event, rule, "闲鱼账号已停用或缺少 Cookie")
                    return
                if not card or not card.enabled:
                    await self._pause_event(session, event, rule, "自动发货卡券已停用或不存在")
                    return
                card_relation = (
                    await session.execute(
                        select(CardItemRelation.id).where(
                            CardItemRelation.user_id == event.user_id,
                            CardItemRelation.card_id == rule.card_id,
                            CardItemRelation.item_id == event.old_item_id,
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                if card_relation is None:
                    await self._pause_event(session, event, rule, "自动发货卡券未关联当前商品")
                    return
                if rule.current_item_id != event.old_item_id:
                    await self._skip_event(session, event, "规则已绑定到更新的商品")
                    return
            else:
                if not account:
                    await self._schedule_migration_retry(
                        session, event, rule, "续售账号已不存在，无法完成关联迁移"
                    )
                    return

            transition_now = get_beijing_now_naive()
            transition = await session.execute(
                update(AutoRelistEvent)
                .where(
                    AutoRelistEvent.id == event.id,
                    AutoRelistEvent.claim_token == token,
                    AutoRelistEvent.status == "claimed",
                )
                .values(
                    status="checking",
                    attempt_count=AutoRelistEvent.attempt_count + 1,
                    updated_at=transition_now,
                )
            )
            if transition.rowcount != 1:
                await session.rollback()
                return
            await session.commit()
            await session.refresh(event)
            try:
                async with distributed_lock(f"auto_relist:{event.user_id}:{event.account_id}", expire=self.lease_seconds, blocking=False) as lock:
                    if not lock.is_locked:
                        if has_published_result:
                            await self._schedule_migration_retry(
                                session, event, rule, "账号续售调度锁被占用"
                            )
                        else:
                            await self._schedule_retry(
                                session, event, rule, "账号续售调度锁被占用"
                            )
                        return
                    lock_stop = asyncio.Event()
                    lock_lost = asyncio.Event()
                    lock_heartbeat = asyncio.create_task(
                        self._lock_heartbeat(lock, lock_stop, "账号", lock_lost)
                    )
                    try:
                        await self._publish_after_check(
                            session, event, rule, material, account, claim_token=token
                        )
                        await session.refresh(event)
                        if lock_lost.is_set() and event.status in {
                            "claimed",
                            "checking",
                            "publishing",
                            "migration_retry",
                        }:
                            if event.publish_state == "succeeded" and event.publish_item_id:
                                await self._schedule_migration_retry(
                                    session,
                                    event,
                                    rule,
                                    "账号续售锁续租失败，等待关联迁移重试",
                                )
                            else:
                                await self._schedule_retry(
                                    session,
                                    event,
                                    rule,
                                    "账号续售锁续租失败，稍后重试",
                                )
                    finally:
                        lock_stop.set()
                        lock_heartbeat.cancel()
                        with suppress(asyncio.CancelledError):
                            await lock_heartbeat
            except Exception as exc:
                if event.publish_state == "succeeded" and event.publish_item_id:
                    await self._schedule_migration_retry(
                        session, event, rule, f"关联迁移执行异常：{exc}"
                    )
                else:
                    await self._schedule_retry(session, event, rule, f"续售执行异常：{exc}")

    async def _publish_after_check(
        self, session, event, rule, material, account, *, claim_token: str
    ) -> None:
        now = get_beijing_now_naive()
        if not await self._renew_event_lease(event.id, claim_token):
            return
        has_published_result = bool(event.publish_state == "succeeded" and event.publish_item_id)
        fetch_result: dict[str, Any] = {}
        if not has_published_result:
            fetch_result = await ItemService(session).fetch_all_items_from_account(
                account=account,
                stop_when_page_all_existing=False,
                fail_on_lock_error=True,
            )
            if fetch_result.get("lock_error"):
                await self._schedule_retry(session, event, rule, fetch_result.get("message") or "账号商品同步锁不可用，稍后重试")
                return
            if fetch_result.get("skipped"):
                await self._schedule_retry(session, event, rule, "确认商品状态时账号同步锁被占用")
                return
            if not fetch_result.get("success"):
                await self._schedule_retry(session, event, rule, f"确认商品状态失败：{fetch_result.get('message') or '未知错误'}")
                return
        else:
            # 已发布事件只补偿本地迁移；若发布后的目录同步尚未看到新商品，
            # 先重新同步一次，避免 migration_retry 因目录缺失永久循环。
            catalog_exists = (
                await session.execute(
                    select(XYCatalogItem.id).where(
                        XYCatalogItem.owner_id == event.user_id,
                        XYCatalogItem.account_pk == account.id,
                        XYCatalogItem.item_id == event.publish_item_id,
                    )
                )
            ).scalar_one_or_none()
            if catalog_exists is None:
                fetch_result = await ItemService(session).fetch_all_items_from_account(
                    account=account,
                    stop_when_page_all_existing=False,
                    fail_on_lock_error=True,
                )
                if fetch_result.get("lock_error") or fetch_result.get("skipped"):
                    await self._schedule_migration_retry(
                        session,
                        event,
                        rule,
                        fetch_result.get("message") or "同步新商品时账号锁被占用，稍后重试",
                    )
                    return
                if not fetch_result.get("success"):
                    await self._schedule_migration_retry(
                        session,
                        event,
                        rule,
                        f"同步新商品失败：{fetch_result.get('message') or '未知错误'}",
                    )
                    return
        await session.refresh(rule)
        if material is not None and not has_published_result:
            await session.refresh(material)
        if not await self._renew_event_lease(event.id, claim_token):
            return
        if not has_published_result and not rule.enabled:
            await self._skip_event(session, event, "自动续售已关闭")
            return
        if (
            rule.user_id != event.user_id
            or rule.material_id != event.material_id
            or (
                not has_published_result
                and (
                    rule.account_id != event.account_id
                    or rule.current_item_id != event.old_item_id
                )
            )
        ):
            if has_published_result:
                await self._schedule_migration_retry(
                    session, event, rule, "自动续售规则归属已更新，等待人工处理已发布商品"
                )
            else:
                await self._skip_event(session, event, "自动续售规则配置已更新")
            return
        if not has_published_result and (material is None or material.user_id != event.user_id or material.is_deleted):
            await self._pause_event(session, event, rule, "素材已移出素材库或归属不一致")
            return
        live_ids = {str(item.get("id") or item.get("item_id") or "").strip() for item in fetch_result.get("items") or []}
        if not has_published_result and event.old_item_id in live_ids:
            event.attempt_count = max(0, int(event.attempt_count or 0) - 1)
            event.status = "pending"
            event.next_retry_at = now + timedelta(seconds=60)
            event.error_message = "旧商品仍在售，等待下一次确认"
            self._release_event_lease(event)
            rule.status = "waiting"
            rule.next_retry_at = event.next_retry_at
            await session.commit()
            return

        if has_published_result:
            new_item_id = event.publish_item_id
        else:
            # 关闭规则与进入平台发布之间用规则行锁串行化：关闭先拿到锁则跳过，
            # 发布先拿到锁并提交状态则按已进入发布中的流程等待结果对账。
            locked_rule = (
                await session.execute(
                    select(AutoRelistRule)
                    .where(
                        AutoRelistRule.id == rule.id,
                        AutoRelistRule.user_id == event.user_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if not locked_rule:
                await self._skip_event(session, event, "自动续售规则不存在")
                return
            rule = locked_rule
            if not rule.enabled:
                await self._skip_event(session, event, "自动续售已关闭")
                return
            publish_request_id = event.publish_request_id or build_publish_request_id(
                event.rule_id, event.order_no, event.old_item_id
            )
            transition = await session.execute(
                update(AutoRelistEvent)
                .where(
                    AutoRelistEvent.id == event.id,
                    AutoRelistEvent.claim_token == claim_token,
                    AutoRelistEvent.status == "checking",
                )
                .values(
                    status="publishing",
                    publish_state="submitted",
                    publish_request_id=publish_request_id,
                    updated_at=get_beijing_now_naive(),
                )
            )
            if transition.rowcount != 1:
                await session.rollback()
                return
            await session.commit()
            await session.refresh(event)
            result = await execute_single_publish(
                session=session,
                user_id=event.user_id,
                account_id=event.account_id,
                item_data=material_to_publish_data(material),
                static_root=Path(self.static_dir),
                publish_request_id=event.publish_request_id,
                source_event_id=event.id,
            )
            lease_alive = await self._renew_event_lease(event.id, claim_token)
            if result.get("unknown"):
                possible_item_id = str(result.get("item_id") or "").strip()
                unknown_message = result.get("message") or "发布结果未知，请人工对账"
                if not await self._persist_unknown_publish_result(
                    session,
                    event,
                    claim_token,
                    unknown_message,
                    possible_item_id or None,
                ):
                    return
                await session.execute(
                    update(AutoRelistRule)
                    .where(
                        AutoRelistRule.id == rule.id,
                        AutoRelistRule.user_id == event.user_id,
                        AutoRelistRule.current_item_id == event.old_item_id,
                        AutoRelistRule.enabled.is_(True),
                    )
                    .values(
                        status="error",
                        next_retry_at=None,
                        last_error=unknown_message[:2000],
                        updated_at=get_beijing_now_naive(),
                    )
                )
                await session.commit()
                return
            new_item_id = str(result.get("item_id") or "").strip()
            if not result.get("success") or not new_item_id:
                if not lease_alive:
                    return
                await self._schedule_retry(session, event, rule, f"重新发布失败：{result.get('message') or '未返回新商品 ID'}")
                return
            if not await self._persist_publish_result(session, event, claim_token, new_item_id):
                return

        if not await self._renew_event_lease(event.id, claim_token):
            return

        migration = await RelistAssociationMigrationService(session).migrate_after_relist(
            owner_id=event.user_id,
            account_id=event.account_id,
            material_id=event.material_id,
            old_item_id=event.old_item_id,
            new_item_id=new_item_id,
            event_id=event.id,
        )
        if not migration.get("success"):
            await self._schedule_migration_retry(
                session, event, rule, migration.get("message") or "关联迁移未完成"
            )
            return
        if not await self._renew_event_lease(event.id, claim_token):
            return
        expected_version = int(rule.version or 0)
        cas_result = await session.execute(update(AutoRelistRule).where(
            AutoRelistRule.id == rule.id,
            AutoRelistRule.version == expected_version,
            AutoRelistRule.current_item_id == event.old_item_id,
            AutoRelistRule.user_id == event.user_id,
        ).values(
            current_item_id=new_item_id,
            last_order_no=event.order_no,
            last_old_item_id=event.old_item_id,
            last_new_item_id=new_item_id,
            last_relisted_at=now,
            status="active" if rule.enabled else "disabled",
            retry_count=0,
            next_retry_at=None,
            last_error=None,
            paused_reason=None,
            version=expected_version + 1,
        ))
        if cas_result.rowcount != 1:
            event.status = "migration_retry"
            event.next_retry_at = now + timedelta(seconds=300)
            event.error_message = "规则已被其他操作更新，等待重新对账"
            self._release_event_lease(event)
            await session.execute(
                update(AutoRelistRule)
                .where(
                    AutoRelistRule.id == rule.id,
                    AutoRelistRule.user_id == event.user_id,
                    AutoRelistRule.version == expected_version,
                    AutoRelistRule.current_item_id == event.old_item_id,
                )
                .values(
                    status="retrying",
                    next_retry_at=event.next_retry_at,
                    last_error=event.error_message,
                    updated_at=now,
                )
            )
            await session.commit()
            return
        event.status = "success"
        event.result_unknown = 0
        event.next_retry_at = None
        event.error_message = None
        self._release_event_lease(event)
        await session.commit()
        logger.info("[自动续售] 成功 event_id={} old_item_id={} new_item_id={}", event.id, event.old_item_id, new_item_id)

auto_relist_task_service = AutoRelistTask(static_dir=get_settings().static_dir)
