"""商品素材自动续售规则管理。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.auto_relist_event import AutoRelistEvent
from common.models.auto_relist_rule import AutoRelistRule
from common.models.card import Card
from common.models.product_material import ProductMaterial
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.models.xy_order import XYOrder
from common.utils.time_utils import get_beijing_now_naive, safe_isoformat


def serialize_auto_relist_rule(rule: AutoRelistRule | None) -> dict[str, Any] | None:
    if not rule:
        return None
    return {
        "id": rule.id,
        "material_id": rule.material_id,
        "account_id": rule.account_id,
        "current_item_id": rule.current_item_id,
        "card_id": rule.card_id,
        "enabled": bool(rule.enabled),
        "delay_seconds": rule.delay_seconds,
        "status": rule.status,
        "retry_count": rule.retry_count,
        "next_retry_at": safe_isoformat(rule.next_retry_at),
        "last_order_no": rule.last_order_no,
        "last_old_item_id": rule.last_old_item_id,
        "last_new_item_id": rule.last_new_item_id,
        "last_error": rule.last_error,
        "last_relisted_at": safe_isoformat(rule.last_relisted_at),
        "created_at": safe_isoformat(rule.created_at),
        "updated_at": safe_isoformat(rule.updated_at),
    }


class AutoRelistRuleService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, material_id: int, user_id: int) -> AutoRelistRule | None:
        result = await self.session.execute(
            select(AutoRelistRule).where(
                AutoRelistRule.material_id == material_id,
                AutoRelistRule.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_map(self, material_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not material_ids:
            return {}
        rows = (
            await self.session.execute(
                select(AutoRelistRule).where(AutoRelistRule.material_id.in_(material_ids))
            )
        ).scalars().all()
        return {int(row.material_id): serialize_auto_relist_rule(row) for row in rows}

    async def save(
        self,
        *,
        material_id: int,
        user_id: int,
        account_id: str,
        current_item_id: str,
        card_id: int,
        enabled: bool,
        delay_seconds: int,
    ) -> AutoRelistRule:
        material = (
            await self.session.execute(
                select(ProductMaterial).where(
                    ProductMaterial.id == material_id,
                    ProductMaterial.user_id == user_id,
                    ProductMaterial.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if not material:
            raise ValueError("商品素材不存在或无权操作")

        account = (
            await self.session.execute(
                select(XYAccount).where(
                    XYAccount.account_id == account_id,
                    XYAccount.owner_id == user_id,
                )
            )
        ).scalars().first()
        if not account:
            raise ValueError("闲鱼账号不存在或无权使用")

        item = (
            await self.session.execute(
                select(XYCatalogItem).where(
                    XYCatalogItem.owner_id == user_id,
                    XYCatalogItem.account_pk == account.id,
                    XYCatalogItem.item_id == current_item_id,
                )
            )
        ).scalar_one_or_none()
        if not item:
            raise ValueError("当前商品不属于所选闲鱼账号，请先获取该账号商品")

        card = (
            await self.session.execute(
                select(Card).where(Card.id == card_id, Card.user_id == user_id)
            )
        ).scalar_one_or_none()
        if not card:
            raise ValueError("自动发货卡券不存在或无权使用")
        if not card.enabled:
            raise ValueError("自动发货卡券已停用，请先启用卡券")

        rule = await self.get(material_id, user_id)
        item_changed = not rule or rule.current_item_id != current_item_id
        if not rule:
            rule = AutoRelistRule(user_id=user_id, material_id=material_id)
            self.session.add(rule)

        rule.account_id = account_id
        rule.current_item_id = current_item_id
        rule.card_id = card_id
        rule.enabled = enabled
        rule.delay_seconds = max(30, min(int(delay_seconds or 60), 3600))
        rule.status = "active" if enabled else "disabled"
        rule.last_error = None
        rule.retry_count = 0
        rule.next_retry_at = None

        if item_changed:
            latest_order = (
                await self.session.execute(
                    select(XYOrder)
                    .where(
                        XYOrder.owner_id == user_id,
                        XYOrder.account_id == account_id,
                        XYOrder.item_id == current_item_id,
                        XYOrder.status.in_(["shipped", "completed"]),
                    )
                    .order_by(desc(XYOrder.updated_at), desc(XYOrder.id))
                    .limit(1)
                )
            ).scalars().first()
            # 新规则从保存时刻开始监听，避免绑定后误处理历史成交。
            rule.last_order_no = latest_order.order_no if latest_order else None

        await self.session.flush()
        await self.session.execute(
            text(
                """
                INSERT IGNORE INTO xy_card_item_relations
                    (user_id, card_id, item_id, source, dock_record_id, created_at, updated_at)
                VALUES (:user_id, :card_id, :item_id, 'own', 0, NOW(), NOW())
                """
            ),
            {"user_id": user_id, "card_id": card_id, "item_id": current_item_id},
        )
        # 兼容仍读取 xy_cards.item_id 的旧逻辑。
        if not card.item_id:
            card.item_id = current_item_id

        if enabled:
            failed_event = (
                await self.session.execute(
                    select(AutoRelistEvent)
                    .where(
                        AutoRelistEvent.rule_id == rule.id,
                        AutoRelistEvent.old_item_id == current_item_id,
                        AutoRelistEvent.status == "failed",
                    )
                    .order_by(desc(AutoRelistEvent.created_at))
                    .limit(1)
                )
            ).scalars().first()
            if failed_event:
                failed_event.status = "retry"
                failed_event.attempt_count = 0
                failed_event.next_retry_at = get_beijing_now_naive()
                failed_event.error_message = None

        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def list_events(self, material_id: int, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        rule = await self.get(material_id, user_id)
        if not rule:
            return []
        rows = (
            await self.session.execute(
                select(AutoRelistEvent)
                .where(AutoRelistEvent.rule_id == rule.id, AutoRelistEvent.user_id == user_id)
                .order_by(desc(AutoRelistEvent.created_at))
                .limit(max(1, min(limit, 100)))
            )
        ).scalars().all()
        return [
            {
                "id": row.id,
                "order_no": row.order_no,
                "old_item_id": row.old_item_id,
                "new_item_id": row.new_item_id,
                "status": row.status,
                "attempt_count": row.attempt_count,
                "error_message": row.error_message,
                "next_retry_at": safe_isoformat(row.next_retry_at),
                "created_at": safe_isoformat(row.created_at),
                "updated_at": safe_isoformat(row.updated_at),
            }
            for row in rows
        ]
