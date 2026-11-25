"""卡券关联管理：整组权限验证、软删除及旧版商品字段撤销。"""
from __future__ import annotations

from itertools import product

from loguru import logger
from sqlalchemy import or_, select, update

from common.models.card import Card
from common.models.card_item_relation import CardItemRelation
from common.services.card_access import (
    CardAccess, CardAccessError, preserved_card_item_ids, relation_access_condition,
)
from common.db.query_conditions import not_deleted


class CardRelations:
    """关联操作共用实现；会话由继承者提供，提交由调用方负责。"""

    async def _lock_item_cards(self, item_ids, user_id: int, extra_card_ids=(), card_id=None) -> set[int]:
        """先锁商品关系涉及的新旧卡券并集；返回已保护的编号，含缺失卡券的历史编号。"""
        relation_stmt = select(CardItemRelation.card_id).where(
            CardItemRelation.item_id.in_(item_ids), CardItemRelation.user_id == user_id,
        )
        legacy_stmt = select(Card.id).where(
            Card.user_id == user_id, not_deleted(Card), Card.item_id.in_(item_ids),
        )
        if card_id is not None:
            relation_stmt = relation_stmt.where(CardItemRelation.card_id == card_id)
            legacy_stmt = legacy_stmt.where(Card.id == card_id)
        planned = set((await self.session.execute(relation_stmt)).scalars().all())
        planned.update((await self.session.execute(legacy_stmt)).scalars().all())
        planned.update(extra_card_ids)
        if planned:
            # 只读取编号，不覆写会话中已加载的内容；归属和状态由后续授权锁读校验。
            await self.session.execute(select(Card.id).where(
                Card.id.in_(planned),
            ).order_by(Card.id).with_for_update())
        return planned

    async def _lock_item_relations(self, item_ids, user_id: int, locked_card_ids, card_id=None):
        """卡券锁定后读取完整关系历史；集合变化时在写入之前拒绝，禁止反向追加卡锁。"""
        stmt = select(CardItemRelation).where(
            CardItemRelation.item_id.in_(item_ids), CardItemRelation.user_id == user_id,
        )
        if card_id is not None:
            stmt = stmt.where(CardItemRelation.card_id == card_id)
        rows = list((await self.session.execute(stmt.order_by(CardItemRelation.id).with_for_update()
                    .execution_options(populate_existing=True))).scalars().all())
        if any(row.card_id not in locked_card_ids for row in rows):
            raise CardAccessError("商品卡券关联已被其他操作更新，请刷新后重试")
        return rows

    async def get_card_item_ids(self, card_id: int, user_id: int | None) -> list[str]:
        """获取授权卡券的本人有效关联；管理员可读取该卡所有关联。"""
        card = (await CardAccess(self.session).require_cards([card_id], user_id))[0]
        stmt = select(CardItemRelation.item_id).join(Card, Card.id == CardItemRelation.card_id).where(
            CardItemRelation.card_id == card_id, not_deleted(CardItemRelation),
            relation_access_condition(),
        )
        if user_id is not None:
            stmt = stmt.where(CardItemRelation.user_id == user_id)
        ids = list(dict.fromkeys((await self.session.execute(stmt)).scalars().all()))
        history = await self.session.scalar(select(CardItemRelation.id).where(
            CardItemRelation.card_id == card_id, CardItemRelation.user_id == card.user_id,
        ).limit(1))
        if not ids and history is None and card.item_id:
            ids.append(card.item_id)
        return ids

    async def _legacy_binding_pairs(self, user_id: int, pairs):
        """为增量绑定保全无本人历史的合法旧商品；调用方须已锁定请求涉及的全部卡券。

        Args:
            user_id: 当前关联所属用户。
            pairs: 已授权的请求商品与卡券组合。
        Returns:
            需要额外迁移的自有旧绑定；不含本次请求已有的绑定。
        """
        own_ids = {value["card_id"] for _, value in pairs
                   if value["source"] == "own" and value["dock_record_id"] == 0}
        if not own_ids:
            return []
        # 只重读已持锁的请求卡券，不能在关系锁之后发现并追加其他卡券锁。
        # 使用当前锁读避免 MySQL 快照遗漏等待卡锁期间已提交的墓碑。
        cards = (await self.session.execute(select(Card.id, Card.item_id).where(
            Card.id.in_(own_ids), Card.user_id == user_id, not_deleted(Card),
        ).order_by(Card.id).with_for_update())).all()
        history_ids = set((await self.session.execute(select(CardItemRelation.card_id).where(
            CardItemRelation.card_id.in_(own_ids), CardItemRelation.user_id == user_id,
        ).order_by(CardItemRelation.id).with_for_update())).scalars().all())
        requested = {(value["card_id"], item_id, value["dock_record_id"]) for item_id, value in pairs}
        preserved = []
        access = CardAccess(self.session)
        for card_id, item_id in cards:
            if not item_id or card_id in history_ids or (card_id, item_id, 0) in requested:
                continue
            # 无目录旧商品仅因这张本人卡的无历史旧字段允许保留；他人目录仍拒绝。
            await access.require_items([item_id], user_id, preserved={item_id})
            preserved.append((item_id, {"card_id": card_id, "source": "own", "dock_record_id": 0}))
        return preserved

    async def _upsert_bindings(self, user_id: int, pairs, *, preserve_legacy: bool = True) -> int:
        """写入已授权、已锁卡券的绑定；增量操作保全旧绑定且不计入请求新增数。

        Args:
            user_id: 当前关联所属用户。
            pairs: 已授权的商品与卡券组合。
            preserve_legacy: 增量绑定默认为真，整张卡明确替换商品时关闭。
        Returns:
            本次请求新增或恢复的关联数，不包含兼容迁移。
        """
        pairs = list(pairs)
        legacy_pairs = await self._legacy_binding_pairs(user_id, pairs) if preserve_legacy else []
        await self._check_binding_conflicts(user_id, [*pairs, *legacy_pairs])
        added = 0
        for pair_index, (item_id, value) in enumerate([*pairs, *legacy_pairs]):
            is_requested = pair_index < len(pairs)
            rows = list((await self.session.execute(select(CardItemRelation).where(
                CardItemRelation.card_id == value["card_id"], CardItemRelation.item_id == item_id,
                or_(CardItemRelation.dock_record_id.is_(None), CardItemRelation.dock_record_id == 0)
                if value["dock_record_id"] == 0
                else CardItemRelation.dock_record_id == value["dock_record_id"],
            ).order_by(CardItemRelation.id).with_for_update().execution_options(populate_existing=True))).scalars().all())
            if any(row.user_id != user_id for row in rows):
                raise CardAccessError("存在其他用户的历史关联，请联系管理员核实")
            # 旧库允许同键 NULL 与 0 并存，优先复用 0，避免把 NULL 改为 0 时冲突。
            row = next((entry for entry in rows if entry.dock_record_id == value["dock_record_id"]), None)
            if row is None and rows:
                row = next((entry for entry in rows if not entry.is_deleted), rows[0])
            if row is None:
                self.session.add(CardItemRelation(user_id=user_id, item_id=item_id, **value))
                added += int(is_requested)
            else:
                if all(entry.is_deleted for entry in rows):
                    added += int(is_requested)
                row.source = value["source"]
                row.dock_record_id = value["dock_record_id"]
                row.is_deleted = False
                duplicates_removed = 0
                for duplicate in rows:
                    if duplicate is not row and not duplicate.is_deleted:
                        duplicate.is_deleted = True
                        duplicates_removed += 1
                if duplicates_removed:
                    logger.info(
                        "归并历史卡券关联: user_id={}, card_id={}, item_id={}, retained_id={}, duplicates_removed={}",
                        user_id, value["card_id"], item_id, row.id, duplicates_removed,
                    )
        await self.session.flush()
        if legacy_pairs:
            logger.info("增量关联保全旧商品绑定: user_id={}, bindings={}", user_id, legacy_pairs)
        return added

    async def _check_binding_conflicts(self, user_id: int, pairs) -> None:
        """在任何修改前检查整组唯一键冲突，禁止借新绑定接管他人历史记录。"""
        if not pairs:
            return
        keys = {(value["card_id"], item_id, value["dock_record_id"]) for item_id, value in pairs}
        rows = (await self.session.execute(select(CardItemRelation).where(
            CardItemRelation.card_id.in_({key[0] for key in keys}),
            CardItemRelation.item_id.in_({key[1] for key in keys}),
        ).order_by(CardItemRelation.id).with_for_update().execution_options(populate_existing=True))).scalars().all()
        if any((row.card_id, row.item_id, row.dock_record_id or 0) in keys
               and row.user_id != user_id for row in rows):
            raise CardAccessError("存在其他用户的历史关联，请联系管理员核实")

    async def update_card_item_relations(self, card_id: int, user_id: int, item_ids) -> dict[str, int]:
        """整组验证后更新自有卡的本人商品绑定，保留合法分销关系。"""
        access = CardAccess(self.session)
        card = (await access.require_cards([card_id], user_id, lock=True))[0]
        history = list((await self.session.execute(select(CardItemRelation).where(
            CardItemRelation.card_id == card_id, CardItemRelation.user_id == user_id,
        ).order_by(CardItemRelation.id).with_for_update().execution_options(populate_existing=True))).scalars().all())
        preserved = preserved_card_item_ids(card_id, user_id, card.item_id, history)
        # 更新自有绑定只撤销合法 own 记录，但授权回退必须检查本人全部历史。
        rows = [row for row in history if row.source in (None, "own")
                and row.dock_record_id in (None, 0)]
        ids = await access.require_items(item_ids, user_id, preserved)
        value = {"card_id": card_id, "source": "own", "dock_record_id": 0}
        pairs = [(item_id, value) for item_id in ids]
        await self._check_binding_conflicts(user_id, pairs)
        desired = set(ids)
        removed = 0
        for row in rows:
            if not row.is_deleted and row.item_id not in desired:
                row.is_deleted = True
                removed += 1
        card.item_id = None
        # 此入口是整张卡的明确替换，不能把用户已移除的旧商品重新迁回。
        added = await self._upsert_bindings(user_id, pairs, preserve_legacy=False)
        logger.info("卡券关联更新: user_id={}, card_id={}, added={}, removed={}", user_id, card_id, added, removed)
        return {"added": added, "removed": removed}

    async def update_item_card_relations(self, item_id: str, user_id: int, card_relations=None) -> dict[str, int]:
        """先验证商品和全部卡券来源，再替换本人关联，失败由调用方回滚。"""
        access = CardAccess(self.session)
        await access.require_items([item_id], user_id)
        # 编号先校验但不持卡锁，再一次性按编号锁新旧并集，不能先锁新卡后追加旧卡。
        requested_cards = await access.require_cards(
            [value.get("card_id") for value in card_relations or []], None,
        )
        locked_card_ids = await self._lock_item_cards(
            [item_id], user_id, [card.id for card in requested_cards],
        )
        values = await access.validate_bindings(user_id, card_relations or [])
        pairs = [(item_id, value) for value in values]
        await self._check_binding_conflicts(user_id, pairs)
        rows = await self._lock_item_relations([item_id], user_id, locked_card_ids)
        desired = {(value["card_id"], value["source"], value["dock_record_id"]) for value in values}
        removed = 0
        for row in rows:
            key = (row.card_id, row.source or "own", row.dock_record_id or 0)
            if not row.is_deleted and key not in desired:
                row.is_deleted = True
                removed += 1
        await self._clear_legacy([item_id], user_id, locked_card_ids=locked_card_ids)
        added = await self._upsert_bindings(user_id, pairs)
        logger.info("商品卡券更新: user_id={}, item_id={}, added={}, removed={}", user_id, item_id, added, removed)
        return {"added": added, "removed": removed}

    async def batch_bind_cards_to_items(self, user_id: int, card_ids, item_ids) -> dict[str, int]:
        """验证全部自有卡券和商品后绑定；任何越权均使整组请求失败。"""
        access = CardAccess(self.session)
        cards = await access.require_cards(card_ids, user_id, lock=True)
        ids = await access.require_items(item_ids, user_id)
        values = [{"card_id": card.id, "source": "own", "dock_record_id": 0} for card in cards]
        added = await self._upsert_bindings(user_id, list(product(ids, values)))
        logger.info("卡券批量绑定: user_id={}, added={}", user_id, added)
        return {"success_count": added, "fail_count": 0}

    async def delete_relations_by_card_id(self, card_id: int, user_id: int) -> int:
        """所有者确认删除卡券后软删除所有关联，包含分销商关联。"""
        await CardAccess(self.session).require_cards([card_id], user_id, lock=True)
        result = await self.session.execute(update(CardItemRelation).where(
            CardItemRelation.card_id == card_id, not_deleted(CardItemRelation),
        ).values(is_deleted=True))
        return result.rowcount

    async def _clear_legacy(self, item_ids, user_id: int, card_id=None, *, locked_card_ids) -> int:
        """仅清除预先锁定的本人旧绑定，避免关系持锁后宽更新取得未知卡券锁。"""
        stmt = update(Card).where(Card.user_id == user_id, not_deleted(Card), Card.item_id.in_(item_ids))
        stmt = stmt.where(Card.id.in_(locked_card_ids))
        if card_id is not None:
            stmt = stmt.where(Card.id == card_id)
        result = await self.session.execute(stmt.values(item_id=None))
        return result.rowcount

    async def delete_relations_by_item_id(self, item_id: str, user_id: int) -> int:
        """验证商品所有者后停用本人全部关联，同时清除本人旧字段。"""
        return await self.batch_delete_relations_by_item_ids([item_id], user_id)

    async def delete_relation_by_card_and_item(self, card_id: int, item_id: str, user_id: int) -> bool:
        """仅允许商品所有者撤销自己的指定关联，卡券内容保持原样。"""
        await CardAccess(self.session).require_items([item_id], user_id)
        locked_card_ids = await self._lock_item_cards([item_id], user_id, card_id=card_id)
        await self._lock_item_relations([item_id], user_id, locked_card_ids, card_id=card_id)
        result = await self.session.execute(update(CardItemRelation).where(
            CardItemRelation.card_id == card_id, CardItemRelation.item_id == item_id,
            CardItemRelation.user_id == user_id, not_deleted(CardItemRelation),
        ).values(is_deleted=True))
        legacy_removed = await self._clear_legacy(
            [item_id], user_id, card_id, locked_card_ids=locked_card_ids,
        )
        success = result.rowcount > 0 or legacy_removed > 0
        logger.info(
            "撤销卡券关联: user_id={}, card_id={}, item_id={}, relations_removed={}, legacy_removed={}, success={}",
            user_id, card_id, item_id, result.rowcount, legacy_removed, success,
        )
        return success

    async def batch_delete_relations_by_item_ids(self, item_ids, user_id: int) -> int:
        """整组验证商品后软删除本人关联，不改动其他用户的同商品标识。"""
        ids = await CardAccess(self.session).require_items(item_ids, user_id)
        locked_card_ids = await self._lock_item_cards(ids, user_id)
        await self._lock_item_relations(ids, user_id, locked_card_ids)
        result = await self.session.execute(update(CardItemRelation).where(
            CardItemRelation.item_id.in_(ids), CardItemRelation.user_id == user_id,
            not_deleted(CardItemRelation),
        ).values(is_deleted=True))
        legacy_removed = await self._clear_legacy(ids, user_id, locked_card_ids=locked_card_ids)
        await self.session.flush()
        logger.info(
            "清空商品卡券关联: user_id={}, item_ids={}, relations_removed={}, legacy_removed={}",
            user_id, ids, result.rowcount, legacy_removed,
        )
        return result.rowcount
