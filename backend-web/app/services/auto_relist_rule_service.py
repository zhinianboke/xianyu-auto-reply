"""商品素材自动续售规则配置服务。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.auto_relist_event import AutoRelistEvent
from common.models.auto_relist_rule import AutoRelistRule
from common.models.card import Card
from common.models.card_item_relation import CardItemRelation
from common.models.product_material import ProductMaterial
from common.models.publish_log import PublishLog
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.utils.time_utils import get_beijing_now_naive
from common.utils.account_status import is_account_active
from app.services.auto_relist_serializers import (
    serialize_auto_relist_event,
    serialize_auto_relist_rule,
)


class AutoRelistRuleService:
    """自动续售规则 CRUD 与权限边界。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, material_id: int, user_id: int | None = None) -> AutoRelistRule | None:
        conditions = [AutoRelistRule.material_id == material_id]
        if user_id is not None:
            conditions.append(AutoRelistRule.user_id == user_id)
        return (await self.session.execute(select(AutoRelistRule).where(*conditions))).scalar_one_or_none()

    async def _get_for_update(self, material_id: int, user_id: int) -> AutoRelistRule | None:
        """在保存规则时锁定当前行，避免并发请求覆盖配置版本。"""
        return (
            await self.session.execute(
                select(AutoRelistRule)
                .where(
                    AutoRelistRule.material_id == material_id,
                    AutoRelistRule.user_id == user_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    async def get_for_material(self, material_id: int) -> AutoRelistRule | None:
        return await self.get(material_id)

    async def get_latest_event(
        self, rule_id: int, user_id: int | None = None
    ) -> AutoRelistEvent | None:
        """获取规则最近一次执行事件，用于展示发布状态和对账提示。"""
        conditions = [AutoRelistEvent.rule_id == rule_id]
        if user_id is not None:
            conditions.append(AutoRelistEvent.user_id == user_id)
        return (
            await self.session.execute(
                select(AutoRelistEvent)
                .where(*conditions)
                .order_by(desc(AutoRelistEvent.created_at), desc(AutoRelistEvent.id))
                .limit(1)
            )
        ).scalar_one_or_none()

    async def get_material_for_owner(self, material_id: int, user_id: int | None = None) -> ProductMaterial | None:
        """查询素材归属，关闭规则时允许素材已经软删除。"""
        conditions = [ProductMaterial.id == material_id]
        if user_id is not None:
            conditions.append(ProductMaterial.user_id == user_id)
        return (await self.session.execute(select(ProductMaterial).where(*conditions))).scalar_one_or_none()

    async def get_map(self, material_ids: list[int], user_id: int | None = None) -> dict[int, dict[str, Any]]:
        if not material_ids:
            return {}
        conditions = [AutoRelistRule.material_id.in_(material_ids)]
        if user_id is not None:
            conditions.append(AutoRelistRule.user_id == user_id)
        rows = (await self.session.execute(select(AutoRelistRule).where(*conditions))).scalars().all()
        if not rows:
            return {}

        # 列表页需要展示最近一次发布/对账状态，批量读取事件避免每个素材触发一次查询。
        rule_ids = [int(row.id) for row in rows]
        event_rows = (
            await self.session.execute(
                select(AutoRelistEvent)
                .where(
                    AutoRelistEvent.rule_id.in_(rule_ids),
                    AutoRelistEvent.user_id.in_([int(row.user_id) for row in rows]),
                )
                .order_by(desc(AutoRelistEvent.created_at), desc(AutoRelistEvent.id))
            )
        ).scalars().all()
        latest_events: dict[int, AutoRelistEvent] = {}
        for event in event_rows:
            latest_events.setdefault(int(event.rule_id), event)
        return {
            int(row.material_id): serialize_auto_relist_rule(
                row,
                latest_event=latest_events.get(int(row.id)),
            )
            for row in rows
        }

    async def save(
        self,
        *,
        material_id: int,
        user_id: int,
        account_id: str | None,
        current_item_id: str | None,
        card_id: int | None,
        enabled: bool,
        delay_seconds: int = 60,
        expected_version: int | None = None,
    ) -> AutoRelistRule:
        """保存规则；关闭分支不依赖账号、商品和卡券仍然存在。"""
        material = (await self.session.execute(select(ProductMaterial).where(
            ProductMaterial.id == material_id, ProductMaterial.user_id == user_id
        ))).scalar_one_or_none()
        if not material:
            raise ValueError("商品素材不存在或无权操作")
        # 版本检查必须和读取放在同一个行锁事务中；否则两个并发保存请求都可能
        # 读到同一版本并先后提交，后提交者会无提示覆盖前者的配置。
        rule = await self._get_for_update(material_id, user_id)
        if not enabled:
            if not rule:
                # 关闭一个不存在的规则仍然是幂等成功语义，由调用方处理 None。
                rule = AutoRelistRule(
                    user_id=user_id,
                    material_id=material_id,
                    account_id=account_id or "",
                    current_item_id=current_item_id or "",
                    card_id=int(card_id or 0),
                    enabled=False,
                    status="disabled",
                    delay_seconds=max(1, int(delay_seconds or 60)),
                )
                self.session.add(rule)
                await self.session.flush()
            elif expected_version is not None and rule.version != expected_version:
                raise ValueError("配置已被其他操作更新，请刷新后重试")
            rule.enabled = False
            rule.status = "disabled"
            rule.next_retry_at = None
            rule.paused_reason = None
            rule.version = int(rule.version or 0) + 1
            await self.session.execute(update(AutoRelistEvent).where(
                AutoRelistEvent.rule_id == rule.id,
                AutoRelistEvent.status.in_(["pending", "retry", "claimed", "checking"]),
            ).values(
                status="skipped",
                error_message="自动续售已关闭",
                next_retry_at=None,
                claim_token=None,
                claimed_at=None,
                lease_expires_at=None,
            ))
            await self.session.commit()
            await self.session.refresh(rule)
            return rule

        if material.is_deleted:
            raise ValueError("素材已移出素材库，不能启用自动续售")
        if not account_id or not current_item_id or not card_id:
            raise ValueError("启用自动续售时必须选择账号、当前商品和卡券")
        if rule:
            # 规则切换到另一个商品时，旧商品的未知发布结果仍可能已经在平台产生
            # 商品。必须先完成人工对账，避免留下孤立商品后又开启新的续售周期。
            unresolved = (
                await self.session.execute(
                    select(AutoRelistEvent.id).where(
                        AutoRelistEvent.rule_id == rule.id,
                        AutoRelistEvent.user_id == user_id,
                        AutoRelistEvent.status.in_(
                            ["unknown", "manual_review", "migration_retry"]
                        ),
                        (
                            (AutoRelistEvent.result_unknown == 1)
                            | (
                                (AutoRelistEvent.status == "migration_retry")
                                & (AutoRelistEvent.publish_state == "succeeded")
                                & AutoRelistEvent.publish_item_id.is_not(None)
                            )
                        ),
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if unresolved is not None:
                raise ValueError("存在尚未完成的自动续售记录，请先完成对账或关联迁移")
        account = (await self.session.execute(select(XYAccount).where(
            XYAccount.account_id == account_id, XYAccount.owner_id == user_id
        ))).scalars().first()
        if not account:
            raise ValueError("闲鱼账号不存在或无权使用")
        if not is_account_active(account.status) or not account.cookie:
            raise ValueError("闲鱼账号已停用或缺少 Cookie，请先恢复账号")
        item = (await self.session.execute(select(XYCatalogItem).where(
            XYCatalogItem.owner_id == user_id, XYCatalogItem.account_pk == account.id, XYCatalogItem.item_id == current_item_id
        ))).scalar_one_or_none()
        if not item:
            raise ValueError("当前商品不属于所选闲鱼账号，请先获取该账号商品")
        card = (await self.session.execute(select(Card).where(Card.id == card_id, Card.user_id == user_id))).scalar_one_or_none()
        if not card:
            raise ValueError("自动发货卡券不存在或无权使用")
        if not card.enabled:
            raise ValueError("自动发货卡券已停用，请先启用卡券")
        if rule and expected_version is not None and rule.version != expected_version:
            raise ValueError("配置已被其他操作更新，请刷新后重试")
        item_changed = not rule or rule.current_item_id != current_item_id
        if not rule:
            rule = AutoRelistRule(user_id=user_id, material_id=material_id)
            self.session.add(rule)
        rule.account_id = account_id
        rule.current_item_id = current_item_id
        rule.card_id = int(card_id)
        rule.enabled = True
        rule.delay_seconds = max(1, int(delay_seconds or 60))
        rule.status = "active"
        rule.last_error = None
        rule.paused_reason = None
        rule.retry_count = 0
        rule.next_retry_at = None
        rule.version = int(rule.version or 0) + 1
        await self.session.flush()
        now = get_beijing_now_naive()
        await self.session.execute(update(AutoRelistEvent).where(
            AutoRelistEvent.rule_id == rule.id,
            AutoRelistEvent.status.in_(["paused", "failed"]),
        ).values(
            status="retry",
            attempt_count=0,
            next_retry_at=now,
            error_message=None,
            claim_token=None,
            claimed_at=None,
            lease_expires_at=None,
        ))
        relation = (await self.session.execute(select(CardItemRelation.id).where(
            CardItemRelation.user_id == user_id,
            CardItemRelation.card_id == int(card_id),
            CardItemRelation.item_id == current_item_id,
        ))).scalar_one_or_none()
        if not relation:
            self.session.add(CardItemRelation(
                user_id=user_id,
                card_id=int(card_id),
                item_id=current_item_id,
                source="own",
                dock_record_id=0,
            ))
        # 保留旧版仅读取 xy_cards.item_id 的兼容路径；关联表仍是完整关系的事实来源。
        if not card.item_id:
            card.item_id = current_item_id
        if item_changed:
            rule.last_order_no = None
            rule.last_order_id = None
            rule.last_order_updated_at = now
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def list_events(self, material_id: int, user_id: int, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        rule = await self.get(material_id, user_id)
        if not rule:
            return {"list": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}
        page = max(1, page)
        page_size = page_size if page_size in (10, 20, 50, 100) else 20
        conditions = [AutoRelistEvent.rule_id == rule.id, AutoRelistEvent.user_id == user_id]
        total = (await self.session.execute(select(func.count()).select_from(AutoRelistEvent).where(*conditions))).scalar() or 0
        rows = (await self.session.execute(select(AutoRelistEvent).where(*conditions)
            .order_by(desc(AutoRelistEvent.created_at)).offset((page - 1) * page_size).limit(page_size))).scalars().all()
        return {
            "list": [serialize_auto_relist_event(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }

    async def list_all_events(
        self,
        *,
        user_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """分页查询自动续售事件，供管理员集中排查未知/失败事件。"""
        page = max(1, int(page or 1))
        page_size = page_size if page_size in (10, 20, 50, 100) else 20
        conditions = []
        if user_id is not None:
            conditions.append(AutoRelistEvent.user_id == user_id)
        if status:
            conditions.append(AutoRelistEvent.status == status)
        total = (
            await self.session.execute(
                select(func.count()).select_from(AutoRelistEvent).where(*conditions)
            )
        ).scalar() or 0
        rows = (
            await self.session.execute(
                select(AutoRelistEvent)
                .where(*conditions)
                .order_by(desc(AutoRelistEvent.created_at), desc(AutoRelistEvent.id))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        data = []
        for row in rows:
            item = serialize_auto_relist_event(row)
            item.update(
                {
                    "rule_id": row.rule_id,
                    "material_id": row.material_id,
                    "account_id": row.account_id,
                    "owner_id": row.user_id,
                    "publish_request_id": row.publish_request_id,
                }
            )
            data.append(item)
        return {
            "list": data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }

    async def reconcile_event(
        self,
        *,
        material_id: int,
        user_id: int,
        event_id: int,
        new_item_id: str | None = None,
        outcome: str = "published",
    ) -> AutoRelistEvent:
        """人工确认未知发布结果，并迁移或释放事件。"""
        if outcome not in {"published", "not_published"}:
            raise ValueError("人工对账结果无效")
        normalized_item_id = str(new_item_id or "").strip()
        if outcome == "published" and not normalized_item_id:
            raise ValueError("请输入新商品 ID")
        event = (
            await self.session.execute(
                select(AutoRelistEvent)
                .where(
                    AutoRelistEvent.id == event_id,
                    AutoRelistEvent.material_id == material_id,
                    AutoRelistEvent.user_id == user_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if not event or event.status not in {"unknown", "manual_review"} or not event.result_unknown:
            raise ValueError("续售记录不存在，或当前记录不需要对账")
        if outcome == "published" and normalized_item_id == event.old_item_id:
            raise ValueError("新商品 ID 不能与旧商品 ID 相同")

        rule = (
            await self.session.execute(
                select(AutoRelistRule).where(
                    AutoRelistRule.id == event.rule_id,
                    AutoRelistRule.user_id == user_id,
                    AutoRelistRule.material_id == material_id,
                )
            )
        ).scalar_one_or_none()
        if not rule:
            raise ValueError("自动续售规则不存在或无权操作")
        if not rule.enabled:
            raise ValueError("自动续售已关闭，请先启用后再确认失败并重试")
        publish_log = None
        if event.publish_request_id:
            publish_log = (
                await self.session.execute(
                    select(PublishLog)
                    .where(PublishLog.publish_request_id == event.publish_request_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
        if outcome == "published":
            known_item_id = str(
                (publish_log.item_id if publish_log else None)
                or event.publish_item_id
                or ""
            ).strip()
            if known_item_id and known_item_id != normalized_item_id:
                raise ValueError("对账商品 ID 与已有发布记录不一致，请核对后重试")
            # 人工确认代表平台已经产生新商品；同步发布日志状态，避免日志仍停留在
            # publishing/unknown，导致幂等查询继续把同一请求误判为待对账。
            if publish_log:
                publish_log.status = "success"
                publish_log.item_id = normalized_item_id
                publish_log.error_message = None
        else:
            # 只有明确确认未发布后才允许释放幂等日志；成功日志与用户确认冲突时拒绝操作。
            if publish_log and publish_log.status == "success" and publish_log.item_id:
                raise ValueError("发布日志已确认成功，不能标记为未发布")
            if publish_log:
                publish_log.status = "failed"
                publish_log.error_message = "人工确认本次续售失败，系统将继续重试发布"
            now = get_beijing_now_naive()
            # 人工确认本次未发布只结束当前未知结果状态，当前订单仍需重新进入发布重试队列。
            event.status = "retry"
            event.publish_state = "not_started"
            event.result_unknown = 0
            event.new_item_id = None
            event.publish_item_id = None
            event.next_retry_at = now
            # 与“标记失败”一致：人工确认未发布是主动介入重发，重置重试预算，避免历史
            # attempt_count 已达上限导致重排后一次失败即被判死。
            event.attempt_count = 0
            event.error_message = "已确认本次续售失败，系统将继续重试发布"
            event.claim_token = None
            event.claimed_at = None
            event.lease_expires_at = None
            # 规则保持监听，当前订单进入重试队列，后续订单仍会继续自动续售。
            rule.status = "retrying" if rule.enabled else "disabled"
            rule.next_retry_at = now if rule.enabled else None
            rule.retry_count = 0
            rule.last_error = event.error_message
            await self.session.commit()
            await self.session.refresh(event)
            return event
        account = (
            await self.session.execute(
                select(XYAccount).where(
                    XYAccount.owner_id == user_id,
                    XYAccount.account_id == event.account_id,
                )
            )
        ).scalars().first()
        if not account:
            raise ValueError("续售账号不存在或无权使用")
        catalog_item = (
            await self.session.execute(
                select(XYCatalogItem.id).where(
                    XYCatalogItem.owner_id == user_id,
                    XYCatalogItem.account_pk == account.id,
                    XYCatalogItem.item_id == normalized_item_id,
                )
            )
        ).scalar_one_or_none()
        if catalog_item is None:
            raise ValueError("新商品不属于该闲鱼账号，请先同步商品后再对账")

        now = get_beijing_now_naive()
        event.new_item_id = normalized_item_id
        event.publish_item_id = normalized_item_id
        event.publish_state = "succeeded"
        event.result_unknown = 0
        event.status = "migration_retry"
        event.next_retry_at = now
        event.error_message = "已人工确认发布结果，等待关联迁移"
        event.claim_token = None
        event.claimed_at = None
        event.lease_expires_at = None
        rule.status = "retrying" if rule.enabled else "disabled"
        rule.next_retry_at = now if rule.enabled else None
        rule.last_error = None
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def mark_event_failed(
        self,
        *,
        material_id: int,
        user_id: int,
        event_id: int,
    ) -> AutoRelistEvent:
        """将发布结果未知的续售事件标记失败，并重新排队发布当前订单。

        标记失败会结束当前未知结果状态，并将当前订单放回立即重试队列；已启用的规则
        仍会继续监听后续订单，后续新订单也可正常触发自动续售。
        """
        event = (
            await self.session.execute(
                select(AutoRelistEvent)
                .where(
                    AutoRelistEvent.id == event_id,
                    AutoRelistEvent.material_id == material_id,
                    AutoRelistEvent.user_id == user_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if not event or event.status not in {"unknown", "manual_review"} or not event.result_unknown:
            raise ValueError("当前续售记录不需要标记失败")

        rule = (
            await self.session.execute(
                select(AutoRelistRule).where(
                    AutoRelistRule.id == event.rule_id,
                    AutoRelistRule.user_id == user_id,
                    AutoRelistRule.material_id == material_id,
                )
            )
        ).scalar_one_or_none()
        if not rule:
            raise ValueError("自动续售规则不存在或无权操作")
        if not rule.enabled:
            raise ValueError("自动续售已关闭，请先启用后再标记失败并重试")

        publish_log = None
        if event.publish_request_id:
            publish_log = (
                await self.session.execute(
                    select(PublishLog)
                    .where(PublishLog.publish_request_id == event.publish_request_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
        if publish_log and publish_log.status == "success" and publish_log.item_id:
            raise ValueError("发布日志已确认成功，不能标记失败")
        if publish_log:
            publish_log.status = "failed"
            publish_log.error_message = "人工标记本次续售失败，系统将继续重试发布"

        now = get_beijing_now_naive()
        # “标记失败”表示本次发布失败，而不是放弃当前订单；重新排队后由执行器继续发布。
        event.status = "retry"
        event.publish_state = "not_started"
        event.result_unknown = 0
        event.new_item_id = None
        event.publish_item_id = None
        event.next_retry_at = now
        # 人工标记失败代表用户主动介入重发，应给一个干净的重试预算；否则历史 attempt_count
        # 可能已达上限，重排后一次失败即被 _schedule_retry 判死，人工干预形同虚设。
        event.attempt_count = 0
        event.error_message = "已标记本次续售失败，系统将继续重试发布；后续订单将继续自动续售"
        event.claim_token = None
        event.claimed_at = None
        event.lease_expires_at = None
        rule.status = "retrying" if rule.enabled else "disabled"
        rule.next_retry_at = now if rule.enabled else None
        rule.retry_count = 0
        rule.last_error = event.error_message if rule.enabled else None
        rule.paused_reason = None
        rule.updated_at = now
        await self.session.commit()
        await self.session.refresh(event)
        return event
