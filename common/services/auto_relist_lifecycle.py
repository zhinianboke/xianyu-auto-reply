"""自动续售事件的状态、租约和重试生命周期辅助方法。"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import uuid

from loguru import logger
from sqlalchemy import or_, select, update

from common.db.session import async_session_maker
from common.models.auto_relist_event import AutoRelistEvent
from common.models.auto_relist_rule import AutoRelistRule
from common.utils.time_utils import get_beijing_now_naive


class AutoRelistLifecycleMixin:
    """为自动续售执行器提供统一的事件状态迁移逻辑。"""

    async def _lock_heartbeat(
        self,
        lock,
        stop_event: asyncio.Event,
        lock_name: str,
        lost_event: asyncio.Event | None = None,
    ) -> None:
        """在长时间同步或发布期间续租 Redis 锁，避免锁自然过期后并发执行。"""
        interval = max(5, self.lease_seconds // 3)
        while True:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                try:
                    extended = await lock.extend(self.lease_seconds)
                except Exception as exc:
                    logger.error("[自动续售] {} 锁续租异常: {}", lock_name, exc)
                    extended = False
                if not extended:
                    logger.warning("[自动续售] {} 锁续租失败", lock_name)
                    if lost_event is not None:
                        lost_event.set()
                    return

    async def _recover_stale_events(self) -> None:
        """兼容旧任务接口名，恢复租约过期事件。"""
        await self._recover_expired_events()

    async def _process_due_events(self) -> None:
        """兼容旧任务接口名，处理当前到期事件。"""
        for event_id in await self._list_due_events():
            await self._process_event(event_id)

    async def _recover_expired_events(self) -> None:
        """恢复租约过期事件：发布前可重试，发布后必须对账。"""
        now = get_beijing_now_naive()
        async with async_session_maker() as session:
            result = await session.execute(
                select(AutoRelistEvent).where(
                    AutoRelistEvent.status.in_(["claimed", "checking", "publishing", "reconciling"]),
                    or_(AutoRelistEvent.lease_expires_at.is_(None), AutoRelistEvent.lease_expires_at < now),
                ).limit(self.batch_size * 2)
            )
            events = result.scalars().all()
            for event in events:
                await self._recover_one_expired_event(session, event, now)
            if events:
                await session.commit()

    async def _list_due_events(self) -> list[int]:
        """读取当前到期且未被租约占用的事件 ID。"""
        now = get_beijing_now_naive()
        async with async_session_maker() as session:
            result = await session.execute(
                select(AutoRelistEvent.id).where(
                    AutoRelistEvent.status.in_(["pending", "retry", "migration_retry"]),
                    or_(AutoRelistEvent.next_retry_at.is_(None), AutoRelistEvent.next_retry_at <= now),
                    or_(AutoRelistEvent.lease_expires_at.is_(None), AutoRelistEvent.lease_expires_at < now),
                ).order_by(AutoRelistEvent.created_at).limit(self.batch_size)
            )
            return list(result.scalars().all())

    async def _claim_event(self, event_id: int) -> str | None:
        """按事件状态和租约原子领取一个到期事件。"""
        now = get_beijing_now_naive()
        token = uuid.uuid4().hex
        lease = now + timedelta(seconds=self.lease_seconds)
        async with async_session_maker() as session:
            result = await session.execute(
                update(AutoRelistEvent)
                .where(
                    AutoRelistEvent.id == event_id,
                    AutoRelistEvent.status.in_(["pending", "retry", "migration_retry"]),
                    or_(AutoRelistEvent.next_retry_at.is_(None), AutoRelistEvent.next_retry_at <= now),
                    or_(AutoRelistEvent.lease_expires_at.is_(None), AutoRelistEvent.lease_expires_at < now),
                )
                .values(
                    status="claimed",
                    claim_token=token,
                    claimed_at=now,
                    lease_expires_at=lease,
                    updated_at=now,
                )
            )
            await session.commit()
            return token if result.rowcount == 1 else None

    async def _recover_one_expired_event(self, session, event, now) -> bool:
        """条件恢复单个过期事件，返回是否成功抢占恢复权。"""
        if event.publish_state == "succeeded" and event.publish_item_id:
            error_message = "任务租约已过期，继续执行关联迁移"
            event_status = "migration_retry"
            event_result_unknown = 0
            event_publish_state = event.publish_state
            event_next_retry_at = now
        elif event.status in {"claimed", "checking"} and event.publish_state in {
            None,
            "not_started",
        }:
            # 领取/检查阶段尚未进入平台发布调用，进程中断不会产生上架副作用，
            # 可安全回到普通重试，避免把能力预检失败误报为未知发布结果。
            error_message = "任务租约已过期，检查未完成，稍后重试"
            event_status = "retry"
            event_result_unknown = 0
            event_publish_state = "not_started"
            event_next_retry_at = now
        else:
            error_message = "任务租约已过期，发布结果需要对账"
            event_status = "unknown"
            event_result_unknown = 1
            event_publish_state = "unknown"
            event_next_retry_at = None
        claim_token = event.claim_token
        statement = update(AutoRelistEvent).where(
            AutoRelistEvent.id == event.id,
            AutoRelistEvent.status.in_(["claimed", "checking", "publishing", "reconciling"]),
            or_(
                AutoRelistEvent.lease_expires_at.is_(None),
                AutoRelistEvent.lease_expires_at < now,
            ),
        )
        statement = statement.where(
            AutoRelistEvent.claim_token == claim_token
            if claim_token
            else AutoRelistEvent.claim_token.is_(None)
        )
        recovered = await session.execute(
            statement.values(
                status=event_status,
                result_unknown=event_result_unknown,
                publish_state=event_publish_state,
                next_retry_at=event_next_retry_at,
                error_message=error_message,
                last_checked_at=now,
                claim_token=None,
                claimed_at=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        if recovered.rowcount != 1:
            return False
        event.status = event_status
        event.result_unknown = event_result_unknown
        event.publish_state = event_publish_state
        event.next_retry_at = event_next_retry_at
        event.error_message = error_message
        event.last_checked_at = now
        self._release_event_lease(event)
        await session.execute(
            update(AutoRelistRule)
            .where(
                AutoRelistRule.id == event.rule_id,
                AutoRelistRule.user_id == event.user_id,
                AutoRelistRule.current_item_id == event.old_item_id,
                AutoRelistRule.enabled.is_(True),
            )
            .values(
                status=(
                    "retrying"
                    if event_status in {"retry", "migration_retry"}
                    else "error"
                ),
                next_retry_at=event_next_retry_at,
                last_error=error_message,
                updated_at=now,
            )
        )
        return True

    async def _skip_event(self, session, event, message: str) -> None:
        """将无需继续执行的事件置为已跳过并释放领取租约。"""
        claim_token = event.claim_token
        values = {
            "status": "skipped",
            "next_retry_at": None,
            "error_message": message,
            "claim_token": None,
            "claimed_at": None,
            "lease_expires_at": None,
            "updated_at": get_beijing_now_naive(),
        }
        statement = update(AutoRelistEvent).where(
            AutoRelistEvent.id == event.id,
            AutoRelistEvent.status.in_(["claimed", "checking", "publishing"]),
        )
        if claim_token:
            statement = statement.where(AutoRelistEvent.claim_token == claim_token)
        result = await session.execute(statement.values(**values))
        if result.rowcount != 1:
            await session.rollback()
            return
        await session.commit()

    async def _pause_event(self, session, event, rule, message: str) -> None:
        """暂停事件及其规则，并保存需要用户处理的原因。"""
        claim_token = event.claim_token
        statement = update(AutoRelistEvent).where(
            AutoRelistEvent.id == event.id,
            AutoRelistEvent.status.in_(["claimed", "checking", "publishing"]),
        )
        if claim_token:
            statement = statement.where(AutoRelistEvent.claim_token == claim_token)
        result = await session.execute(
            statement.values(
                status="paused",
                next_retry_at=None,
                error_message=message,
                claim_token=None,
                claimed_at=None,
                lease_expires_at=None,
                updated_at=get_beijing_now_naive(),
            )
        )
        if result.rowcount != 1:
            await session.rollback()
            return
        # 关闭规则与 worker 并发时只允许 enabled=true 的规则进入 paused，
        # 避免旧 worker 把用户刚关闭的规则改回可执行状态。
        await session.execute(
            update(AutoRelistRule)
            .where(
                AutoRelistRule.id == rule.id,
                AutoRelistRule.user_id == event.user_id,
                AutoRelistRule.enabled.is_(True),
                AutoRelistRule.current_item_id == event.old_item_id,
            )
            .values(
                status="paused",
                next_retry_at=None,
                paused_reason=message,
                last_error=message,
                updated_at=get_beijing_now_naive(),
            )
        )
        await session.commit()

    @staticmethod
    def _release_event_lease(event: AutoRelistEvent) -> None:
        """事件离开领取态后释放租约，使下一次重试可按 next_retry_at 执行。"""
        event.claim_token = None
        event.claimed_at = None
        event.lease_expires_at = None

    async def _renew_event_lease(self, event_id: int, claim_token: str) -> bool:
        """续租并校验领取令牌，防止过期 worker 覆盖新状态。"""
        now = get_beijing_now_naive()
        lease = now + timedelta(seconds=self.lease_seconds)
        async with async_session_maker() as session:
            result = await session.execute(
                update(AutoRelistEvent)
                .where(
                    AutoRelistEvent.id == event_id,
                    AutoRelistEvent.claim_token == claim_token,
                    AutoRelistEvent.status.in_(
                        ["claimed", "checking", "publishing", "migration_retry"]
                    ),
                )
                .values(lease_expires_at=lease, last_checked_at=now, updated_at=now)
            )
            await session.commit()
            return result.rowcount == 1

    async def _persist_publish_result(
        self, session, event, claim_token: str, new_item_id: str
    ) -> bool:
        """在领取令牌仍有效时持久化已确认的平台商品 ID。"""
        now = get_beijing_now_naive()
        result = await session.execute(
            update(AutoRelistEvent)
            .where(
                AutoRelistEvent.id == event.id,
                AutoRelistEvent.claim_token == claim_token,
                AutoRelistEvent.status == "publishing",
            )
            .values(
                publish_state="succeeded",
                publish_item_id=new_item_id,
                new_item_id=new_item_id,
                last_checked_at=now,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            await session.rollback()
            return False
        await session.commit()
        await session.refresh(event)
        return True

    async def _persist_unknown_publish_result(
        self,
        session,
        event,
        claim_token: str,
        message: str,
        possible_item_id: str | None = None,
    ) -> bool:
        """持久化未知发布结果；若有平台商品 ID 同时保留供人工对账。"""
        now = get_beijing_now_naive()
        values = {
            "status": "unknown",
            "result_unknown": 1,
            "publish_state": "unknown",
            "error_message": message[:2000],
            "next_retry_at": None,
            "last_checked_at": now,
            "claim_token": None,
            "claimed_at": None,
            "lease_expires_at": None,
            "updated_at": now,
        }
        if possible_item_id:
            values["publish_item_id"] = possible_item_id
            values["new_item_id"] = possible_item_id
        result = await session.execute(
            update(AutoRelistEvent)
            .where(
                AutoRelistEvent.id == event.id,
                AutoRelistEvent.claim_token == claim_token,
                AutoRelistEvent.status == "publishing",
            )
            .values(**values)
        )
        if result.rowcount != 1:
            await session.rollback()
            return False
        await session.commit()
        await session.refresh(event)
        return True

    async def _schedule_retry(self, session, event, rule, message: str) -> None:
        """记录可再次发布的失败并按尝试次数安排退避重试。"""
        now = get_beijing_now_naive()
        delays = (60, 300, 900)
        attempt = max(1, int(event.attempt_count or 0))
        error_message = message[:2000]
        if attempt >= self.max_retries:
            event_status, next_retry_at = "failed", None
            rule_status, rule_next_retry_at = "error", None
        else:
            event_status = "retry"
            delay = delays[min(attempt - 1, len(delays) - 1)]
            next_retry_at = now + timedelta(seconds=delay)
            rule_status, rule_next_retry_at = "retrying", next_retry_at
        claim_token = event.claim_token
        statement = update(AutoRelistEvent).where(
            AutoRelistEvent.id == event.id,
            AutoRelistEvent.status.in_(["claimed", "checking", "publishing"]),
        )
        if claim_token:
            statement = statement.where(AutoRelistEvent.claim_token == claim_token)
        result = await session.execute(
            statement.values(
                status=event_status,
                next_retry_at=next_retry_at,
                error_message=error_message,
                claim_token=None,
                claimed_at=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            await session.rollback()
            return
        await session.execute(
            update(AutoRelistRule)
            .where(
                AutoRelistRule.id == rule.id,
                AutoRelistRule.user_id == event.user_id,
                AutoRelistRule.enabled.is_(True),
                AutoRelistRule.current_item_id == event.old_item_id,
            )
            .values(
                retry_count=attempt,
                status=rule_status,
                next_retry_at=rule_next_retry_at,
                last_error=error_message,
                updated_at=now,
            )
        )
        await session.commit()

    async def _schedule_migration_retry(self, session, event, rule, message: str) -> None:
        """记录已发布商品的本地关联迁移失败，仅重试迁移而不再次发布。"""
        now = get_beijing_now_naive()
        next_retry_at = now + timedelta(seconds=300)
        error_message = str(message)[:2000]
        claim_token = event.claim_token
        statement = update(AutoRelistEvent).where(
            AutoRelistEvent.id == event.id,
            AutoRelistEvent.status.in_(
                ["claimed", "checking", "publishing", "migration_retry"]
            ),
        )
        if claim_token:
            statement = statement.where(AutoRelistEvent.claim_token == claim_token)
        result = await session.execute(
            statement.values(
                status="migration_retry",
                next_retry_at=next_retry_at,
                error_message=error_message,
                claim_token=None,
                claimed_at=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            await session.rollback()
            return
        await session.execute(
            update(AutoRelistRule)
            .where(
                AutoRelistRule.id == rule.id,
                AutoRelistRule.user_id == event.user_id,
                AutoRelistRule.enabled.is_(True),
                AutoRelistRule.current_item_id == event.old_item_id,
            )
            .values(
                status="retrying",
                next_retry_at=next_retry_at,
                last_error=error_message,
                updated_at=now,
            )
        )
        await session.execute(
            update(AutoRelistRule)
            .where(
                AutoRelistRule.id == rule.id,
                AutoRelistRule.user_id == event.user_id,
                AutoRelistRule.enabled.is_(False),
            )
            .values(
                status="disabled",
                next_retry_at=None,
                last_error=error_message,
                updated_at=now,
            )
        )
        await session.commit()

    async def _mark_runner_lock_unavailable(self) -> None:
        """Redis 调度锁不可用时，把到期事件转为可见的延迟重试。"""
        now = get_beijing_now_naive()
        async with async_session_maker() as session:
            rows = (
                await session.execute(
                    select(AutoRelistEvent).where(
                        AutoRelistEvent.status.in_(["pending", "retry", "migration_retry"]),
                        or_(AutoRelistEvent.next_retry_at.is_(None), AutoRelistEvent.next_retry_at <= now),
                        or_(AutoRelistEvent.lease_expires_at.is_(None), AutoRelistEvent.lease_expires_at < now),
                    ).limit(self.batch_size * 2)
                )
            ).scalars().all()
            for event in rows:
                is_migration = event.status == "migration_retry"
                event.status = "migration_retry" if is_migration else "retry"
                event.next_retry_at = now + timedelta(seconds=300 if is_migration else 60)
                event.error_message = "自动续售调度锁不可用，稍后重试"
                await session.execute(
                    update(AutoRelistRule)
                    .where(
                        AutoRelistRule.id == event.rule_id,
                        AutoRelistRule.user_id == event.user_id,
                        AutoRelistRule.enabled.is_(True),
                    )
                    .values(
                        status="retrying",
                        next_retry_at=event.next_retry_at,
                        last_error=event.error_message,
                        updated_at=now,
                    )
                )
            if rows:
                await session.commit()
