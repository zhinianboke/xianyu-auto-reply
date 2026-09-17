"""自动续售订单发现逻辑。"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from common.db.session import async_session_maker
from common.models.auto_relist_event import AutoRelistEvent
from common.models.auto_relist_rule import AutoRelistRule
from common.models.xy_order import XYOrder
from common.services.auto_relist_utils import build_publish_request_id, naive_beijing
from common.utils.time_utils import get_beijing_now_naive


class AutoRelistDiscoveryMixin:
    """为自动续售执行器提供订单游标和事件去重。"""

    async def _discover_events(self) -> None:
        """扫描符合条件的订单并幂等创建续售事件。"""
        now = get_beijing_now_naive()
        async with async_session_maker() as session:
            rules = (
                await session.execute(
                    select(AutoRelistRule).where(
                        AutoRelistRule.enabled.is_(True),
                        AutoRelistRule.status.notin_(["error", "paused"]),
                    )
                )
            ).scalars().all()
            for rule in rules:
                active_event = (
                    await session.execute(
                        select(AutoRelistEvent.id)
                        .where(
                            AutoRelistEvent.rule_id == rule.id,
                            AutoRelistEvent.old_item_id == rule.current_item_id,
                            AutoRelistEvent.status.in_(
                                [
                                    "pending",
                                    "claimed",
                                    "checking",
                                    "publishing",
                                    "retry",
                                    "migration_retry",
                                    "unknown",
                                    "reconciling",
                                    "manual_review",
                                ]
                            ),
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if active_event is not None:
                    continue
                order_conditions = [
                    XYOrder.owner_id == rule.user_id,
                    XYOrder.account_id == rule.account_id,
                    XYOrder.item_id == rule.current_item_id,
                    or_(
                        and_(
                            XYOrder.status.in_(["shipped", "completed"]),
                            XYOrder.delivery_method == "auto",
                            XYOrder.delivery_content.is_not(None),
                            XYOrder.delivery_content != "",
                            ~XYOrder.delivery_content.op("regexp")(r"^[[:space:]]*$"),
                        ),
                        and_(
                            XYOrder.card_only_delivered.is_(True),
                            XYOrder.delivery_method.in_(["auto", "scheduled"]),
                            XYOrder.delivery_content.is_not(None),
                            XYOrder.delivery_content != "",
                            ~XYOrder.delivery_content.op("regexp")(r"^[[:space:]]*$"),
                            XYOrder.status.notin_(["cancelled", "refunded", "refunding"]),
                        ),
                    ),
                ]
                cursor_time = naive_beijing(rule.last_order_updated_at)
                if cursor_time is not None:
                    order_conditions.append(
                        or_(
                            XYOrder.updated_at > cursor_time,
                            and_(
                                XYOrder.updated_at == cursor_time,
                                XYOrder.id > int(getattr(rule, "last_order_id", 0) or 0),
                            ),
                        )
                    )
                order = (
                    await session.execute(
                        select(XYOrder)
                        .where(*order_conditions)
                        .order_by(XYOrder.updated_at.asc(), XYOrder.id.asc())
                        .limit(1)
                    )
                ).scalars().first()
                if not order:
                    continue
                order_updated_at = naive_beijing(order.updated_at) or now
                event = AutoRelistEvent(
                    user_id=rule.user_id,
                    rule_id=rule.id,
                    material_id=rule.material_id,
                    account_id=rule.account_id,
                    order_no=order.order_no,
                    old_item_id=rule.current_item_id,
                    status="pending",
                    next_retry_at=max(
                        now, order_updated_at + timedelta(seconds=rule.delay_seconds)
                    ),
                    publish_request_id=build_publish_request_id(
                        rule.id, order.order_no, rule.current_item_id
                    ),
                )
                try:
                    async with session.begin_nested():
                        session.add(event)
                        await session.flush()
                except IntegrityError:
                    duplicate = (
                        await session.execute(
                            select(AutoRelistEvent.id)
                            .where(
                                or_(
                                    and_(
                                        AutoRelistEvent.rule_id == rule.id,
                                        AutoRelistEvent.order_no == order.order_no,
                                    ),
                                    AutoRelistEvent.publish_request_id
                                    == event.publish_request_id,
                                )
                            )
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                    if duplicate is None:
                        raise
                    rule.last_order_no = order.order_no
                    rule.last_order_id = order.id
                    rule.last_order_updated_at = order_updated_at
                    continue
                rule.status = "waiting"
                rule.next_retry_at = event.next_retry_at
                rule.last_order_no = order.order_no
                rule.last_order_id = order.id
                rule.last_order_updated_at = order_updated_at
            await session.commit()
    async def _recover_legacy_manual_failed_events(self) -> None:
        """恢复旧版本将人工标记失败写成终态的事件，避免历史续售永久停止。"""
        now = get_beijing_now_naive()
        async with async_session_maker() as session:
            events = (
                await session.execute(
                    select(AutoRelistEvent).where(
                        AutoRelistEvent.status == "failed",
                        AutoRelistEvent.error_message.like("%本次续售不再重试%"),
                    )
                )
            ).scalars().all()
            if not events:
                return
            for event in events:
                event.status = "retry"
                event.next_retry_at = now
                event.attempt_count = 0
                event.error_message = "已恢复历史人工标记失败记录，系统将继续重试发布"
                event.claim_token = None
                event.claimed_at = None
                event.lease_expires_at = None
                await session.execute(
                    update(AutoRelistRule)
                    .where(
                        AutoRelistRule.id == event.rule_id,
                        AutoRelistRule.user_id == event.user_id,
                        AutoRelistRule.enabled.is_(True),
                    )
                    .values(
                        status="retrying",
                        next_retry_at=now,
                        last_error=event.error_message,
                        updated_at=now,
                    )
                )
            await session.commit()


__all__ = ["AutoRelistDiscoveryMixin"]
