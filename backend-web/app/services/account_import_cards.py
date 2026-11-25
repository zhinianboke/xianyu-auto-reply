"""账号 Excel 卡券导入：先整组校验来源和商品归属，只刷新，事务由导入入口统一提交。"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from app.services.account_import_parsing import _parse_bool, _parse_int, _parse_str, _read_sheet_rows
from common.models.card import Card
from common.models.card_item_relation import CardItemRelation
from common.services.card_access import CardAccess, CardAccessError, preserved_card_item_ids
from common.services.card_matcher import CardMatcher
from common.db.query_conditions import not_deleted


class AccountCardImportMixin:
    """复用导入入口的会话及用户映射，权限校验失败时整次导入回滚。"""

    async def _import_cards(self, wb) -> None:
        """导入卡券"""
        rows = _read_sheet_rows(wb, "卡券")
        for row in rows:
            name = _parse_str(row.get("卡券名称"))
            if not name:
                continue
            card_type = _parse_str(row.get("类型")) or "text"
            spec_value = _parse_str(row.get("规格值"))

            # 按 名称+规格值 查找
            stmt = select(Card).where(
                Card.user_id == self.owner_id,
                Card.name == name,
                not_deleted(Card),
            )
            if spec_value:
                stmt = stmt.where(Card.spec_value == spec_value)
            else:
                stmt = stmt.where((Card.spec_value.is_(None)) | (Card.spec_value == ""))

            result = await self.session.execute(stmt)
            existing = result.scalars().first()

            if existing:
                existing.type = card_type
                existing.enabled = _parse_bool(row.get("启用"))
                existing.delay_seconds = _parse_int(row.get("延迟秒数"), 0)
                existing.is_multi_spec = _parse_bool(row.get("多规格"))
                existing.spec_name = _parse_str(row.get("规格名")) or existing.spec_name
                existing.spec_value = spec_value or existing.spec_value
                existing.api_config = _parse_str(row.get("API配置")) or existing.api_config
                existing.text_content = _parse_str(row.get("文本内容")) or existing.text_content
                existing.data_content = _parse_str(row.get("数据内容")) or existing.data_content
                existing.image_url = _parse_str(row.get("图片URL")) or existing.image_url
                existing.image_urls = _parse_str(row.get("多图片URL")) or existing.image_urls
                self.session.add(existing)
                self._card_name_spec_to_id[f"{name}|{spec_value}"] = existing.id
            else:
                card = Card(
                    user_id=self.owner_id,
                    name=name,
                    type=card_type,
                    enabled=_parse_bool(row.get("启用")),
                    delay_seconds=_parse_int(row.get("延迟秒数"), 0),
                    is_multi_spec=_parse_bool(row.get("多规格")),
                    spec_name=_parse_str(row.get("规格名")) or None,
                    spec_value=spec_value or None,
                    api_config=_parse_str(row.get("API配置")) or None,
                    text_content=_parse_str(row.get("文本内容")) or None,
                    data_content=_parse_str(row.get("数据内容")) or None,
                    image_url=_parse_str(row.get("图片URL")) or None,
                    image_urls=_parse_str(row.get("多图片URL")) or None,
                )
                self.session.add(card)
                await self.session.flush()
                self._card_name_spec_to_id[f"{name}|{spec_value}"] = card.id

        await self.session.flush()

        # 补充映射：查询所有该用户的卡券
        stmt = select(Card.id, Card.name, Card.spec_value).where(
            Card.user_id == self.owner_id, not_deleted(Card),
        )
        result = await self.session.execute(stmt)
        for card_id, card_name, card_spec in result.all():
            key = f"{card_name}|{card_spec or ''}"
            self._card_name_spec_to_id[key] = card_id

    async def _import_card_item_relations(self, wb) -> None:
        """导入卡券商品关联"""
        rows = _read_sheet_rows(wb, "卡券商品关联")
        pending = []
        for row in rows:
            card_name = _parse_str(row.get("卡券名称"))
            item_id = _parse_str(row.get("商品ID"))
            if not card_name or not item_id:
                continue
            source = _parse_str(row.get("来源")) or "own"
            if source != "own":
                raise CardAccessError("当前账号导入格式不支持对接卡券关联，请在商品页面重新选择对接卡券")

            # 查找卡券ID（先精确匹配名称，不带规格）
            card_id = None
            for key, cid in self._card_name_spec_to_id.items():
                if key.startswith(f"{card_name}|"):
                    card_id = cid
                    break
            if not card_id:
                continue

            pending.append({
                "card_id": card_id, "item_id": item_id,
                "source": source, "dock_record_id": None,
            })

        # 导入整组关联前先验证授权；拒绝时不得写入部分关系。
        access = CardAccess(self.session)
        normalized = await access.validate_bindings(self.owner_id, pending)
        authorized_by_card = {binding["card_id"]: binding for binding in normalized}
        # 只保留同一张本人卡券已存在的有效自有关联，避免借另一张卡的历史
        # 商品编号新建无目录关联；墓碑或无效来源不能作为保留授权。
        card_ids = list(authorized_by_card)
        history = (await self.session.execute(select(CardItemRelation).where(
            CardItemRelation.card_id.in_(card_ids),
            CardItemRelation.user_id == self.owner_id,
        ).with_for_update().execution_options(populate_existing=True))).scalars().all() if card_ids else []
        by_card = {card_id: [] for card_id in card_ids}
        items_by_card = {card_id: [] for card_id in card_ids}
        for relation in history:
            by_card[relation.card_id].append(relation)
        for binding in pending:
            items_by_card[binding["card_id"]].append(binding["item_id"])
        # 上面的整组授权已锁定卡券；这里只读取回退字段，避免再次加载大内容。
        cards = (await self.session.execute(select(Card.id, Card.item_id).where(
            Card.id.in_(card_ids), Card.user_id == self.owner_id,
            not_deleted(Card),
        ))).all() if card_ids else []
        for card_id, legacy_item_id in cards:
            preserved = preserved_card_item_ids(card_id, self.owner_id, legacy_item_id, by_card[card_id])
            await access.require_items(items_by_card[card_id], self.owner_id, preserved)
        pairs = [(binding["item_id"], authorized_by_card[binding["card_id"]]) for binding in pending]
        # 复用公共 upsert：恢复本人的软删除关联，并在写入前拒绝他人历史键。
        added = await CardMatcher(self.session)._upsert_bindings(self.owner_id, pairs)
        await self.session.flush()
        logger.info("卡券关联导入完成：owner_id={}，新增或恢复={}，请求行数={}", self.owner_id, added, len(pairs))
