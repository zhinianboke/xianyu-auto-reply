"""卡券对象权限：统一校验自有卡券、商品归属和有效分销授权。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import aliased

from common.models.card import Card
from common.models.card_item_relation import CardItemRelation
from common.models.dock_record import DockRecord
from common.models.xy_catalog_item import XYCatalogItem
from common.db.query_conditions import not_deleted


class CardAccessError(ValueError):
    """卡券对象不存在、越权或关联参数非法，消息可直接展示给用户。"""


def preserved_card_item_ids(card_id: int, user_id: int, legacy_item_id, history) -> set[str]:
    """计算可原样保留的商品；传入该卡完整历史，返回本人有效自有关联或无历史旧字段。"""
    relations = [row for row in history if row.card_id == card_id and row.user_id == user_id]
    preserved = {
        row.item_id for row in relations
        if not row.is_deleted and row.source in (None, "own")
        and row.dock_record_id in (None, 0)
    }
    # 非法来源、分销记录和墓碑也属于本人历史，不能据旧字段新增未知商品绑定。
    if not relations and legacy_item_id:
        preserved.add(legacy_item_id)
    return preserved


def dock_access_condition(dock=DockRecord):
    """返回可用对接的公共 SQL 条件；参数为对接模型或别名，卡券由外层查询提供。"""
    parent = aliased(DockRecord)
    parent_valid = exists(select(parent.id).where(
        parent.id == dock.parent_dock_id,
        parent.card_id == Card.id,
        parent.user_id == dock.source_user_id,
        parent.level == 1,
        parent.status.is_(True),
        parent.owner_disabled == 0,
        parent.allow_sub_dock.is_(True),
    ).correlate(Card, dock))
    return and_(
        not_deleted(Card), Card.is_dockable.is_(True), Card.enabled.is_(True),
        dock.card_id == Card.id, dock.status.is_(True), dock.owner_disabled == 0,
        or_(dock.level == 1, and_(dock.level == 2, parent_valid)),
    )


def relation_access_condition():
    """返回关联授权 SQL 条件；以关联用户验证自有卡或公共有效对接链。"""
    dock = aliased(DockRecord)
    own = and_(
        or_(CardItemRelation.source.is_(None), CardItemRelation.source == "own"),
        Card.user_id == CardItemRelation.user_id,
        or_(CardItemRelation.dock_record_id.is_(None), CardItemRelation.dock_record_id == 0),
    )
    dock_valid = exists(select(dock.id).where(
        dock.id == CardItemRelation.dock_record_id,
        dock.user_id == CardItemRelation.user_id,
        dock_access_condition(dock),
        or_(
            and_(CardItemRelation.source == "dock_l1", dock.level == 1),
            and_(CardItemRelation.source == "dock_l2", dock.level == 2),
        ),
    ))
    return or_(own, dock_valid)


class CardAccess:
    """复用业务会话校验整组对象；所有校验均在业务变更之前执行。"""

    def __init__(self, session):
        """保存调用方会话；不创建连接或提交事务。"""
        self.session = session

    async def require_cards(self, card_ids, user_id: int | None, lock=False) -> list[Card]:
        """校验全部卡券归属并返回卡对象；None 仅供管理员读取使用。"""
        ids = list(dict.fromkeys(card_ids))
        if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in ids):
            raise CardAccessError("卡券编号无效")
        if not ids:
            return []
        stmt = select(Card).where(Card.id.in_(ids), not_deleted(Card))
        if user_id is not None:
            stmt = stmt.where(Card.user_id == user_id)
        if lock:
            # 锁读必须刷新 identity map，不能沿用网络等待前缓存的归属和启停状态。
            stmt = stmt.order_by(Card.id).with_for_update().execution_options(populate_existing=True)
        cards = list((await self.session.execute(stmt)).scalars().all())
        by_id = {card.id: card for card in cards}
        if len(by_id) != len(ids):
            raise CardAccessError("卡券不存在或无权操作")
        return [by_id[value] for value in ids]

    async def require_items(self, item_ids, user_id: int, preserved=None) -> list[str]:
        """校验整组商品；仅已验证关联中的无目录商品允许原样保留。"""
        if user_id is None:
            raise CardAccessError("缺少商品所属用户，无法验证权限")
        ids = list(dict.fromkeys(item_ids))
        if any(not isinstance(value, str) or not value.strip() or len(value) > 64 for value in ids):
            raise CardAccessError("商品编号不能为空且不能超过64个字符")
        if not ids:
            return []
        rows = (await self.session.execute(select(
            XYCatalogItem.item_id, XYCatalogItem.owner_id,
        ).where(XYCatalogItem.item_id.in_(ids)))).all()
        own = {item_id for item_id, owner_id in rows if owner_id == user_id}
        existing = {item_id for item_id, _ in rows}
        allowed = own | (set(preserved or ()) - existing)
        if not set(ids).issubset(allowed):
            raise CardAccessError("商品不存在或无权操作")
        return ids

    async def _lock_binding_docks(self, user_id: int, dock_ids) -> tuple[dict, dict]:
        """先探测链结构，再按一级、二级顺序锁读；结构并发变化时拒绝使用旧授权。"""
        if not dock_ids:
            return {}, {}
        probe = (await self.session.execute(select(
            DockRecord.id, DockRecord.level, DockRecord.parent_dock_id,
        ).where(DockRecord.id.in_(dock_ids), DockRecord.user_id == user_id))).all()
        planned = {dock_id: (level, parent_id) for dock_id, level, parent_id in probe}
        parent_ids = {parent_id for level, parent_id in planned.values() if level == 2 and parent_id is not None}
        root_ids = parent_ids | {dock_id for dock_id, (level, _) in planned.items() if level == 1}
        roots = {}
        if root_ids:
            rows = (await self.session.execute(select(DockRecord).where(
                DockRecord.id.in_(root_ids), DockRecord.level == 1,
            ).order_by(DockRecord.id).with_for_update().execution_options(populate_existing=True))).scalars().all()
            roots = {dock.id: dock for dock in rows}
        docks = {dock_id: dock for dock_id, dock in roots.items()
                 if dock_id in dock_ids and dock.user_id == user_id}
        child_ids = set(dock_ids) - root_ids
        if child_ids:
            rows = (await self.session.execute(select(DockRecord).where(
                DockRecord.id.in_(child_ids), DockRecord.user_id == user_id, DockRecord.level == 2,
            ).order_by(DockRecord.id).with_for_update().execution_options(populate_existing=True))).scalars().all()
            docks.update({dock.id: dock for dock in rows})
        # 所有状态和父链均来自刷新后的锁读；父链变更不能在子锁之后追加父锁。
        for dock_id, dock in docks.items():
            if planned.get(dock_id) != (dock.level, dock.parent_dock_id):
                raise CardAccessError("对接关系已被其他操作更新，请刷新后重试")
        if any(dock_id not in docks for dock_id in planned):
            raise CardAccessError("对接关系已被其他操作更新，请刷新后重试")
        return docks, {dock_id: dock for dock_id, dock in roots.items() if dock_id in parent_ids}

    async def validate_bindings(self, user_id: int, card_relations) -> list[dict[str, Any]]:
        """校验全部来源、卡券及对接链，去重后返回规范化的关联负载。"""
        normalized = []
        seen = set()
        for value in card_relations:
            card_id = value.get("card_id")
            source = value.get("source") or "own"
            dock_id = value.get("dock_record_id") or 0
            if (not isinstance(card_id, int) or isinstance(card_id, bool) or card_id <= 0
                    or source not in ("own", "dock_l1", "dock_l2")
                    or not isinstance(dock_id, int) or isinstance(dock_id, bool) or dock_id < 0):
                raise CardAccessError("卡券来源或编号无效")
            if (source == "own" and dock_id != 0) or (source != "own" and dock_id == 0):
                raise CardAccessError("卡券来源与对接记录不匹配")
            key = (card_id, source, dock_id)
            if key not in seen:
                normalized.append({"card_id": card_id, "source": source, "dock_record_id": dock_id})
                seen.add(key)
        cards = await self.require_cards([value["card_id"] for value in normalized], None, lock=True)
        by_id = {card.id: card for card in cards}
        dock_ids = {value["dock_record_id"] for value in normalized if value["source"] != "own"}
        docks, parents = await self._lock_binding_docks(user_id, dock_ids)
        for value in normalized:
            card = by_id[value["card_id"]]
            if value["source"] == "own":
                if card.user_id != user_id:
                    raise CardAccessError("卡券不存在或无权操作")
                continue
            dock = docks.get(value["dock_record_id"])
            level = 1 if value["source"] == "dock_l1" else 2
            if (dock is None or dock.card_id != card.id or dock.level != level
                    or not dock.status or dock.owner_disabled or not card.enabled or not card.is_dockable):
                raise CardAccessError("对接记录不存在、已停用或无权使用该卡券")
            if level == 2:
                parent = parents.get(dock.parent_dock_id)
                if (parent is None or parent.card_id != card.id or parent.user_id != dock.source_user_id
                        or parent.level != 1 or not parent.status or parent.owner_disabled or not parent.allow_sub_dock):
                    raise CardAccessError("上级对接已停用或不允许下级使用")
        return normalized
