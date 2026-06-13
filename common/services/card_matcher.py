"""
统一卡券匹配服务

功能：
1. 提供统一的卡券查询方法（通过关联表查询，含向后兼容回退）
2. 提供统一的规格匹配逻辑（完全匹配 > 名称匹配 > 通用卡券）
3. 提供批量查询商品卡券配置状态
4. 被 backend-web、websocket、scheduler 三个服务统一调用

匹配优先级：
- 完全匹配：spec_name + spec_value 都匹配
- 名称匹配：仅 spec_name 匹配（暂未启用，保留扩展）
- 通用卡券：is_multi_spec=False 的卡券
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.card import Card
from common.models.card_item_relation import CardItemRelation


from common.utils.time_utils import safe_isoformat
class CardMatcher:
    """统一卡券匹配器"""

    # TTL 缓存：{cache_key: (timestamp, data)}
    _cache: Dict[tuple, tuple] = {}
    _CACHE_TTL = 300  # 5 分钟

    def __init__(self, session: AsyncSession):
        """
        初始化卡券匹配器
        
        Args:
            session: 异步数据库会话
        """
        self.session = session

    @classmethod
    def _get_cache_key(cls, item_id: str, spec_name: Optional[str], spec_value: Optional[str]) -> tuple:
        """生成缓存键"""
        return (item_id, spec_name or '', spec_value or '')

    @classmethod
    def _get_cached(cls, key: tuple) -> Optional[List[Dict[str, Any]]]:
        """从缓存获取数据（未过期时）"""
        if key in cls._cache:
            ts, data = cls._cache[key]
            if time.monotonic() - ts < cls._CACHE_TTL:
                logger.debug(f"卡券缓存命中: {key}")
                return data
            del cls._cache[key]
        return None

    @classmethod
    def _set_cache(cls, key: tuple, data: List[Dict[str, Any]]) -> None:
        """写入缓存"""
        cls._cache[key] = (time.monotonic(), data)

    @classmethod
    def clear_cache_for_item(cls, item_id: str) -> int:
        """清除指定商品ID的所有缓存条目
        
        Args:
            item_id: 商品ID
            
        Returns:
            清除的条目数
        """
        keys_to_remove = [k for k in cls._cache if k[0] == item_id]
        for k in keys_to_remove:
            del cls._cache[k]
        if keys_to_remove:
            logger.debug(f"卡券缓存已清除: item_id={item_id}, 条目数={len(keys_to_remove)}")
        return len(keys_to_remove)

    @classmethod
    def clear_all_cache(cls) -> None:
        """清除所有缓存"""
        cls._cache.clear()
        logger.debug("卡券缓存已全部清除")

    async def get_cards_by_item_id(
        self,
        item_id: str,
        spec_name: Optional[str] = None,
        spec_value: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        根据商品ID获取匹配的卡券列表（统一入口）
        
        查询顺序：
        1. 优先从 xy_card_item_relations 关联表查询（含 source/dock_record_id）
        2. 关联表无数据时，回退到 xy_cards.item_id 字段（向后兼容）
        3. 对查询结果进行规格匹配过滤
        
        注意：同一个 card_id 可能有多条关联记录（不同 source），每条都会单独返回。
        
        Args:
            item_id: 商品ID
            spec_name: 规格名称（可选，用于多规格匹配）
            spec_value: 规格值（可选，用于多规格匹配）
            
        Returns:
            匹配的卡券字典列表（每条含 card_source 和 dock_record_id）
        """
        # 检查缓存
        cache_key = self._get_cache_key(item_id, spec_name, spec_value)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # 1. 优先从关联表查询（返回 Card+source+dock_record_id 元组，不去重）
        relation_rows = await self._query_cards_with_source(item_id)
        
        if relation_rows:
            # 关联表有数据：每行转为字典，附带 source 信息
            all_cards = []
            for card, card_source, dock_record_id in relation_rows:
                card_dict = self._card_to_dict(card)
                card_dict["card_source"] = card_source or "own"
                card_dict["dock_record_id"] = dock_record_id
                all_cards.append(card_dict)
            
            # 规格匹配过滤（对字典列表过滤）
            matched = self._match_cards_by_spec(all_cards, spec_name, spec_value)
            # 按 card.id 去重（发货场景下同一张卡券视为一张）：
            # 关联表可能因历史数据冗余或对接关系存在多条同 card_id 记录
            matched = self._dedup_cards_by_id(matched)
            logger.info(
                f"卡券匹配: item_id={item_id}, 来源=关联表, "
                f"查询到={len(all_cards)}条, 规格过滤/去重后={len(matched)}张, "
                f"spec_name={spec_name}, spec_value={spec_value}"
            )
            self._set_cache(cache_key, matched)
            return matched
        
        # 2. 关联表无数据，回退到旧字段
        legacy_cards = await self._query_cards_from_legacy(item_id)
        if not legacy_cards:
            logger.info(f"卡券匹配: item_id={item_id}, 未找到任何卡券")
            self._set_cache(cache_key, [])
            return []
        
        matched = self._match_cards_from_objects(legacy_cards, spec_name, spec_value)
        for card_dict in matched:
            card_dict["card_source"] = "own"
            card_dict["dock_record_id"] = None
        # 旧字段来源理论上不会重复，但保持一致行为
        matched = self._dedup_cards_by_id(matched)
        
        logger.info(
            f"卡券匹配: item_id={item_id}, 来源=旧字段, "
            f"查询到={len(legacy_cards)}张, 规格过滤/去重后={len(matched)}张, "
            f"spec_name={spec_name}, spec_value={spec_value}"
        )
        self._set_cache(cache_key, matched)
        return matched

    @staticmethod
    def _dedup_cards_by_id(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按 card.id 去重，优先保留 card_source='own' 的记录
        
        场景：同一张卡券可能因历史数据冗余或对接关系在关联表有多条记录，
        发货/匹配场景下应视为同一张卡券，避免误报"多卡冲突"。
        
        Args:
            cards: 卡券字典列表
            
        Returns:
            去重后的卡券字典列表（保持原顺序，但 own 源优先）
        """
        # 第一轮：收集每个 card_id 的最优记录（own 优先，否则首个）
        best_by_id: Dict[Any, Dict[str, Any]] = {}
        order: List[Any] = []
        for c in cards:
            cid = c.get("id")
            if cid is None:
                continue
            source = c.get("card_source") or "own"
            if cid not in best_by_id:
                best_by_id[cid] = c
                order.append(cid)
            elif source == "own" and best_by_id[cid].get("card_source") != "own":
                # 遇到 own 源，替换之前的非 own 记录
                best_by_id[cid] = c
        return [best_by_id[cid] for cid in order]

    async def get_all_cards_by_item_id(self, item_id: str) -> List[Dict[str, Any]]:
        """
        获取商品关联的所有卡券（管理展示用，不过滤启用状态和规格）
        
        与 get_cards_by_item_id 不同，此方法：
        1. 不过滤 Card.enabled，返回启用和禁用的卡券
        2. 不做规格匹配，返回所有规格的卡券
        3. 返回关联表中的 source 和 dock_record_id
        
        Args:
            item_id: 商品ID
            
        Returns:
            所有关联的卡券字典列表（含 card_source, dock_record_id）
        """
        # 1. 优先从关联表查询（不过滤 enabled），同时取出 source 和 dock_record_id
        stmt = (
            select(Card, CardItemRelation.source, CardItemRelation.dock_record_id)
            .join(
                CardItemRelation,
                Card.id == CardItemRelation.card_id,
            )
            .where(CardItemRelation.item_id == item_id)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        
        if rows:
            cards_out = []
            for row in rows:
                card_dict = self._card_to_dict(row[0])
                card_dict["card_source"] = row[1] or "own"
                card_dict["dock_record_id"] = row[2]
                cards_out.append(card_dict)
            return cards_out
        
        # 2. 关联表无数据，回退到旧字段（不过滤 enabled）
        legacy_stmt = select(Card).where(Card.item_id == item_id)
        legacy_result = await self.session.execute(legacy_stmt)
        cards = list(legacy_result.scalars().all())
        
        result_list = []
        for card in cards:
            card_dict = self._card_to_dict(card)
            card_dict["card_source"] = "own"
            card_dict["dock_record_id"] = None
            result_list.append(card_dict)
        return result_list

    async def get_card_item_ids(self, card_id: int) -> List[str]:
        """
        获取卡券关联的所有商品ID列表
        
        Args:
            card_id: 卡券ID
            
        Returns:
            商品ID列表
        """
        stmt = select(CardItemRelation.item_id).where(
            CardItemRelation.card_id == card_id
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_items_with_card_status(
        self,
        item_ids: List[str],
    ) -> Dict[str, bool]:
        """
        批量查询商品是否配置了卡券（不区分用户，与发货配置弹窗查询逻辑一致）
        
        Args:
            item_ids: 商品ID列表
            
        Returns:
            {item_id: True/False} 字典
        """
        if not item_ids:
            return {}
        
        # 从关联表查询
        relation_items: set = set()
        try:
            stmt = select(CardItemRelation.item_id).where(
                CardItemRelation.item_id.in_(item_ids),
            ).distinct()
            result = await self.session.execute(stmt)
            relation_items = {row[0] for row in result.all()}
        except Exception as e:
            logger.warning(f"从关联表查询卡券状态失败（回退到旧字段）: {e}")
        
        # 从旧字段查询（向后兼容）
        legacy_stmt = select(Card.item_id).where(
            Card.item_id.in_(item_ids),
            Card.enabled == True,
        ).distinct()
        legacy_result = await self.session.execute(legacy_stmt)
        legacy_items = {row[0] for row in legacy_result.all() if row[0]}
        
        # 合并结果
        configured_items = relation_items | legacy_items
        logger.info(f"卡券状态查询: 查询商品数={len(item_ids)}, 关联表命中={len(relation_items)}, 旧字段命中={len(legacy_items)}, 总命中={len(configured_items)}")
        return {item_id: item_id in configured_items for item_id in item_ids}

    async def update_card_item_relations(
        self,
        card_id: int,
        user_id: int,
        item_ids: List[str],
    ) -> Dict[str, int]:
        """
        更新卡券的商品关联关系（先删旧关联再插新关联，同一事务）
        
        Args:
            card_id: 卡券ID
            user_id: 用户ID
            item_ids: 新的商品ID列表
            
        Returns:
            {"added": 新增数量, "removed": 删除数量}
        """
        # 删除旧关联
        delete_result = await self.session.execute(
            text("DELETE FROM xy_card_item_relations WHERE card_id = :card_id"),
            {"card_id": card_id}
        )
        removed = delete_result.rowcount
        
        # 插入新关联
        added = 0
        for item_id in item_ids:
            if not item_id:
                continue
            await self.session.execute(
                text("""
                    INSERT IGNORE INTO xy_card_item_relations 
                    (user_id, card_id, item_id, dock_record_id, created_at, updated_at)
                    VALUES (:user_id, :card_id, :item_id, 0, NOW(), NOW())
                """),
                {"user_id": user_id, "card_id": card_id, "item_id": item_id}
            )
            added += 1
        
        await self.session.flush()
        # 清除受影响商品的缓存
        for iid in item_ids:
            self.clear_cache_for_item(iid)
        return {"added": added, "removed": removed}

    async def update_item_card_relations(
        self,
        item_id: str,
        user_id: int,
        card_relations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, int]:
        """
        更新商品关联的卡券列表（先删旧关联再插新关联）
        
        Args:
            item_id: 商品ID
            user_id: 用户ID
            card_relations: 卡券关联列表，每个元素含 card_id, source, dock_record_id
            
        Returns:
            {"added": 新增数量, "removed": 删除数量}
        """
        # 删除旧关联
        delete_result = await self.session.execute(
            text("DELETE FROM xy_card_item_relations WHERE item_id = :item_id"),
            {"item_id": item_id}
        )
        removed = delete_result.rowcount
        
        # 插入新关联（允许同一 card_id 多条记录，通过 source+dock_record_id 区分）
        added = 0
        for rel in (card_relations or []):
            card_id = rel.get("card_id")
            if not card_id:
                continue
            source = rel.get("source", "own")
            dock_record_id = rel.get("dock_record_id") or 0
            await self.session.execute(
                text("""
                    INSERT INTO xy_card_item_relations 
                    (user_id, card_id, item_id, source, dock_record_id, created_at, updated_at)
                    VALUES (:user_id, :card_id, :item_id, :source, :dock_record_id, NOW(), NOW())
                """),
                {"user_id": user_id, "card_id": card_id, "item_id": item_id,
                 "source": source, "dock_record_id": dock_record_id}
            )
            added += 1
        
        await self.session.flush()
        # 清除受影响商品的缓存
        self.clear_cache_for_item(item_id)
        return {"added": added, "removed": removed}

    async def batch_bind_cards_to_items(
        self,
        user_id: int,
        card_ids: List[int],
        item_ids: List[str],
    ) -> Dict[str, int]:
        """
        批量绑定卡券到商品（INSERT IGNORE 避免重复）
        
        Args:
            user_id: 用户ID
            card_ids: 卡券ID列表
            item_ids: 商品ID列表
            
        Returns:
            {"success_count": 成功数量, "fail_count": 失败数量}
        """
        success_count = 0
        fail_count = 0
        
        for card_id in card_ids:
            for item_id in item_ids:
                if not item_id:
                    continue
                try:
                    result = await self.session.execute(
                        text("""
                            INSERT IGNORE INTO xy_card_item_relations 
                            (user_id, card_id, item_id, dock_record_id, created_at, updated_at)
                            VALUES (:user_id, :card_id, :item_id, 0, NOW(), NOW())
                        """),
                        {"user_id": user_id, "card_id": card_id, "item_id": item_id}
                    )
                    if result.rowcount > 0:
                        success_count += 1
                except Exception as e:
                    logger.warning(f"绑定卡券 {card_id} 到商品 {item_id} 失败: {e}")
                    fail_count += 1
        
        await self.session.flush()
        # 清除受影响商品的缓存
        for iid in item_ids:
            self.clear_cache_for_item(iid)
        return {"success_count": success_count, "fail_count": fail_count}

    async def delete_relations_by_card_id(self, card_id: int) -> int:
        """
        删除卡券的所有关联记录（级联删除）
        
        Args:
            card_id: 卡券ID
            
        Returns:
            删除的记录数
        """
        result = await self.session.execute(
            text("DELETE FROM xy_card_item_relations WHERE card_id = :card_id"),
            {"card_id": card_id}
        )
        self.clear_all_cache()  # card_id 级别无法精确对应 item_id，清全量
        return result.rowcount

    async def delete_relations_by_item_id(self, item_id: str) -> int:
        """
        删除商品的所有关联记录（级联删除）
        
        Args:
            item_id: 商品ID
            
        Returns:
            删除的记录数
        """
        result = await self.session.execute(
            text("DELETE FROM xy_card_item_relations WHERE item_id = :item_id"),
            {"item_id": item_id}
        )
        self.clear_cache_for_item(item_id)
        return result.rowcount

    async def delete_relation_by_card_and_item(self, card_id: int, item_id: str) -> bool:
        """
        删除指定卡券与指定商品的关联记录
        
        Args:
            card_id: 卡券ID
            item_id: 商品ID
            
        Returns:
            是否成功删除
        """
        result = await self.session.execute(
            text("DELETE FROM xy_card_item_relations WHERE card_id = :card_id AND item_id = :item_id"),
            {"card_id": card_id, "item_id": item_id}
        )
        removed = result.rowcount
        if removed > 0:
            logger.info(f"删除卡券-商品关联: card_id={card_id}, item_id={item_id}")
        self.clear_cache_for_item(item_id)
        return removed > 0

    async def batch_delete_relations_by_item_ids(self, item_ids: List[str]) -> int:
        """
        批量清空多个商品的所有卡券关联记录（同时清空旧字段 xy_cards.item_id）
        
        Args:
            item_ids: 商品ID列表
            
        Returns:
            删除的关联表记录总数
        """
        if not item_ids:
            return 0
        # 1. 删除关联表记录
        del_stmt = text(
            "DELETE FROM xy_card_item_relations WHERE item_id IN :item_ids"
        ).bindparams(bindparam("item_ids", expanding=True))
        result = await self.session.execute(del_stmt, {"item_ids": item_ids})
        removed = result.rowcount
        
        # 2. 清空旧字段 xy_cards.item_id（向后兼容，置为 NULL）
        upd_stmt = text(
            "UPDATE xy_cards SET item_id = NULL WHERE item_id IN :item_ids"
        ).bindparams(bindparam("item_ids", expanding=True))
        await self.session.execute(upd_stmt, {"item_ids": item_ids})
        
        await self.session.flush()
        logger.info(f"批量清空商品关联卡券: 商品数={len(item_ids)}, 删除关联记录={removed}")
        for iid in item_ids:
            self.clear_cache_for_item(iid)
        return removed

    # ==================== 内部方法 ====================

    async def _query_cards_with_source(self, item_id: str) -> List[tuple]:
        """
        从关联表查询商品关联的启用卡券，同时返回 source 和 dock_record_id。
        不使用 .scalars() 以避免 SQLAlchemy identity map 去重。
        
        Args:
            item_id: 商品ID
            
        Returns:
            [(Card, source, dock_record_id), ...] 元组列表
        """
        stmt = (
            select(Card, CardItemRelation.source, CardItemRelation.dock_record_id)
            .join(
                CardItemRelation,
                Card.id == CardItemRelation.card_id,
            )
            .where(
                CardItemRelation.item_id == item_id,
                Card.enabled == True,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.all())

    async def _query_cards_from_legacy(self, item_id: str) -> List[Card]:
        """
        从 xy_cards.item_id 字段查询（向后兼容回退）
        
        Args:
            item_id: 商品ID
            
        Returns:
            Card 对象列表
        """
        stmt = select(Card).where(
            Card.item_id == item_id,
            Card.enabled == True,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _match_cards_by_spec(
        card_dicts: List[Dict[str, Any]],
        spec_name: Optional[str],
        spec_value: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        根据规格信息过滤匹配的卡券（统一字典版）
        
        匹配规则：
        - 有规格信息时：多规格卡券需 spec_name+spec_value 完全匹配
        - 无规格信息时：只返回非多规格卡券（通用卡券）
        
        Args:
            card_dicts: 卡券字典列表
            spec_name: 规格名称
            spec_value: 规格值
            
        Returns:
            匹配的卡券字典列表
        """
        matched = []
        has_spec_info = bool(spec_name and spec_value)
        
        for cd in card_dicts:
            if cd.get("is_multi_spec"):
                if has_spec_info:
                    card_sn = (cd.get("spec_name") or '').strip().lower()
                    card_sv = (cd.get("spec_value") or '').strip().lower()
                    input_sn = spec_name.strip().lower()
                    input_sv = spec_value.strip().lower()
                    
                    if card_sn == input_sn and card_sv == input_sv:
                        matched.append(cd)
                        logger.info(f"多规格卡券匹配成功: {cd.get('name')} [{spec_name}:{spec_value}]")
                    else:
                        logger.debug(
                            f"多规格卡券匹配失败: 卡券[{cd.get('spec_name')}:{cd.get('spec_value')}] "
                            f"vs 订单[{spec_name}:{spec_value}]"
                        )
            else:
                if not has_spec_info:
                    matched.append(cd)
        
        return matched

    def _match_cards_from_objects(
        self,
        cards: List[Card],
        spec_name: Optional[str],
        spec_value: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Card 对象版规格匹配：先转字典再统一过滤"""
        card_dicts = [self._card_to_dict(c) for c in cards]
        return self._match_cards_by_spec(card_dicts, spec_name, spec_value)

    @staticmethod
    def _card_to_dict(card: Card) -> Dict[str, Any]:
        """
        将 Card 对象转换为字典
        
        Args:
            card: Card 对象
            
        Returns:
            卡券字典
        """
        # 解析 api_config JSON
        api_config = None
        if card.api_config:
            try:
                api_config = json.loads(card.api_config)
            except (json.JSONDecodeError, TypeError):
                api_config = card.api_config

        # 解析 image_urls JSON
        image_urls = None
        if card.image_urls:
            try:
                image_urls = json.loads(card.image_urls)
            except (json.JSONDecodeError, TypeError):
                image_urls = None

        return {
            "id": card.id,
            "user_id": card.user_id,
            "item_id": card.item_id,
            "name": card.name,
            "type": card.type,
            "description": card.description,
            "enabled": card.enabled,
            "delay_seconds": card.delay_seconds or 0,
            "delivery_count": card.delivery_count,
            "is_multi_spec": card.is_multi_spec or False,
            "spec_name": card.spec_name,
            "spec_value": card.spec_value,
            "api_config": api_config,
            "text_content": card.text_content,
            "data_content": card.data_content,
            "image_url": card.image_url,
            "image_urls": image_urls,
            "created_at": safe_isoformat(card.created_at),
            "updated_at": safe_isoformat(card.updated_at),
        }
