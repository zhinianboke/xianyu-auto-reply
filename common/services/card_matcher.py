"""统一卡券匹配：按实际用户验证来源授权，隔离管理展示与发货内容。"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import exists, select
from sqlalchemy.orm import load_only

from common.models.card import Card
from common.models.card_item_relation import CardItemRelation
from common.services.card_access import CardAccess, CardAccessError, relation_access_condition
from common.services.card_relations import CardRelations
from common.services.card_serialization import CardSerializationMixin


class CardMatcher(CardRelations, CardSerializationMixin):
    """公共匹配器：关联管理共用 CardRelations，始终使用调用方会话。"""

    def __init__(self, session):
        """接收请求或任务会话，不创建连接池、不提交事务。"""
        self.session = session

    async def _authorized_rows(self, item_ids, user_id: int | None, enabled: bool, *, lite=False):
        """批量查询经来源授权的活跃关联；enabled 控制是否仅取启用卡券。"""
        stmt = select(Card, CardItemRelation).join(
            CardItemRelation, Card.id == CardItemRelation.card_id,
        ).where(
            CardItemRelation.item_id.in_(item_ids), CardItemRelation.is_deleted.is_(False),
            Card.is_deleted.is_(False), relation_access_condition(),
        )
        if user_id is not None:
            stmt = stmt.where(CardItemRelation.user_id == user_id)
        if enabled:
            stmt = stmt.where(Card.enabled.is_(True))
        if lite:
            stmt = stmt.options(load_only(Card.id, Card.item_id))
        return list((await self.session.execute(stmt)).all())

    async def _legacy_cards(self, item_ids, user_id: int | None, enabled: bool, *, lite=False):
        """仅回退无任何关联历史的自有卡券；墓碑、无效来源均不能触发回退。"""
        history = exists(select(CardItemRelation.id).where(
            CardItemRelation.card_id == Card.id, CardItemRelation.user_id == Card.user_id,
        ))
        stmt = select(Card).where(Card.item_id.in_(item_ids), Card.is_deleted.is_(False), ~history)
        if user_id is not None:
            stmt = stmt.where(Card.user_id == user_id)
        if enabled:
            stmt = stmt.where(Card.enabled.is_(True))
        if lite:
            stmt = stmt.options(load_only(Card.id, Card.item_id))
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_cards_by_item_id(self, item_id: str, spec_name=None, spec_value=None, *, user_id: int):
        """以真实订单/账号用户匹配启用卡券；返回授权后的发货内容和来源。"""
        if user_id is None:
            raise CardAccessError("缺少发货所属用户，无法验证卡券权限")
        rows = await self._authorized_rows([item_id], user_id, True)
        if rows:
            cards = [self._relation_to_dict(card, relation, include_content=True) for card, relation in rows]
        else:
            cards = [self._legacy_to_dict(card) for card in await self._legacy_cards([item_id], user_id, True)]
        matched = self._dedup_cards_by_id(self._match_card_dicts_by_spec(cards, spec_name, spec_value))
        logger.info("卡券匹配: user_id={}, item_id={}, matched={}, spec_name={}, spec_value={}",
                    user_id, item_id, len(matched), spec_name, spec_value)
        return matched

    async def get_all_cards_by_item_id(self, item_id: str, user_id: int | None):
        """管理读取只展示本人商品关联；对接卡券只返回选择所需公开字段。"""
        if user_id is not None:
            await CardAccess(self.session).require_items([item_id], user_id)
        rows = await self._authorized_rows([item_id], user_id, False)
        if rows:
            return [self._relation_to_dict(card, relation, include_content=(
                user_id is None or card.user_id == user_id
            )) for card, relation in rows]
        return [self._legacy_to_dict(card) for card in await self._legacy_cards([item_id], user_id, False)]

    async def get_items_with_card_status(self, item_ids, user_id: int | None):
        """批量计算授权卡券配置状态；不返回完整卡密用于界面展示。"""
        if not item_ids:
            return {}
        rows = await self._authorized_rows(item_ids, user_id, False, lite=True)
        configured = {relation.item_id for _, relation in rows}
        legacy = await self._legacy_cards(item_ids, user_id, True, lite=True)
        configured.update(card.item_id for card in legacy)
        return {item_id: item_id in configured for item_id in item_ids}

    @staticmethod
    def _dedup_cards_by_id(cards):
        """同一张卡只发一次，保留顺序并优先本人自有来源。"""
        best = {}
        for card in cards:
            card_id = card["id"]
            if card_id not in best or card.get("card_source") == "own":
                best[card_id] = card
        return list(best.values())

    @staticmethod
    def _match_card_dicts_by_spec(cards, spec_name, spec_value):
        """共用原有规格规则：有完整规格只选精确多规格，无规格只选通用卡。"""
        has_spec = bool(spec_name and spec_value)
        expected = ((spec_name or "").strip().lower(), (spec_value or "").strip().lower())
        return [card for card in cards if (
            bool(card.get("is_multi_spec")) == has_spec and (not has_spec or (
                (card.get("spec_name") or "").strip().lower(),
                (card.get("spec_value") or "").strip().lower(),
            ) == expected)
        )]

    def _relation_to_dict(self, card, relation, *, include_content):
        """授权关联转管理或发货字典；供货方内容不暴露给分销商管理接口。"""
        result = self._card_to_dict_simple(card)
        result["card_source"] = relation.source or "own"
        result["dock_record_id"] = relation.dock_record_id or 0
        if not include_content:
            for key in ("api_config", "text_content", "data_content", "image_url", "image_urls", "description"):
                result[key] = None
            result["item_id"] = None
            result["type"] = "api"
        return result

    def _legacy_to_dict(self, card):
        """自有旧字段卡转字典并补齐来源，保持存量接口字段兼容。"""
        result = self._card_to_dict_simple(card)
        result.update(card_source="own", dock_record_id=None)
        return result
