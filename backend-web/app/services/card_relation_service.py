"""卡券商品关联服务，将当前用户权限传入公共匹配器后统一提交事务。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from common.services.card_matcher import CardMatcher


class CardRelationMixin:
    """提供关联查询和管理方法，由 CardService 统一持有数据库会话。"""

    async def get_cards_by_item_id(self, user_id: int | None, item_id: str) -> List[Dict[str, Any]]:
        """获取指定商品关联的所有卡券列表（管理展示用，不过滤启用状态和规格）
        
        Args:
            user_id: 用户ID，None表示查询所有用户（管理员）
            item_id: 商品ID
        """
        matcher = CardMatcher(self.session)
        return await matcher.get_all_cards_by_item_id(item_id, user_id)

    async def get_cards_by_item_id_and_spec(
        self,
        item_id: str,
        spec_name: Optional[str] = None,
        spec_value: Optional[str] = None,
        *,
        user_id: int,
    ) -> List[Dict[str, Any]]:
        """根据商品ID和规格获取卡券列表（用于发货匹配，委托给CardMatcher）
        
        Args:
            item_id: 商品ID
            user_id: 实际订单或账号所属用户ID
            spec_name: 规格名称（可选）
            spec_value: 规格值（可选）
            
        Returns:
            匹配的卡券列表
        """
        matcher = CardMatcher(self.session)
        return await matcher.get_cards_by_item_id(item_id, spec_name, spec_value, user_id=user_id)

    async def batch_clear_item_relations(self, item_ids: List[str], user_id: int) -> int:
        """批量清空商品的卡券关联关系（不删除卡券本身）
        
        Args:
            item_ids: 商品ID列表
            
        Returns:
            删除的关联记录总数
        """
        matcher = CardMatcher(self.session)
        removed = await matcher.batch_delete_relations_by_item_ids(item_ids, user_id)
        await self.session.commit()
        return removed

    async def delete_card_item_relation(self, card_id: int, item_id: str, user_id: int) -> bool:
        """删除指定卡券与指定商品的关联关系
        
        Args:
            card_id: 卡券ID
            item_id: 商品ID
            
        Returns:
            是否成功删除
        """
        matcher = CardMatcher(self.session)
        success = await matcher.delete_relation_by_card_and_item(card_id, item_id, user_id)
        await self.session.commit()
        return success

    async def update_item_card_relations(
        self,
        item_id: str,
        user_id: int,
        card_relations: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """更新商品关联的卡券列表（先删旧关联再插新关联）
        
        Args:
            item_id: 商品ID
            user_id: 用户ID
            card_relations: 卡券关联列表，每个元素含 card_id, source, dock_record_id
            
        Returns:
            {"added": 新增数量, "removed": 删除数量}
        """
        matcher = CardMatcher(self.session)
        result = await matcher.update_item_card_relations(item_id, user_id, card_relations=card_relations)
        await self.session.commit()
        return result

    async def batch_bind_cards_to_items(
        self,
        user_id: int,
        card_ids: List[int],
        item_ids: List[str],
    ) -> Dict[str, int]:
        """批量绑定卡券到商品（通过关联表，不再复制卡券）
        
        Args:
            user_id: 用户ID
            card_ids: 卡券ID列表
            item_ids: 商品ID列表
            
        Returns:
            {"success_count": 成功数量, "fail_count": 失败数量}
        """
        matcher = CardMatcher(self.session)
        result = await matcher.batch_bind_cards_to_items(user_id, card_ids, item_ids)
        await self.session.commit()
        return result

    async def update_card_item_relations(
        self,
        card_id: int,
        user_id: int,
        item_ids: List[str],
    ) -> Dict[str, int]:
        """更新卡券的商品关联关系
        
        Args:
            card_id: 卡券ID
            user_id: 用户ID
            item_ids: 新的商品ID列表
            
        Returns:
            {"added": 新增数量, "removed": 删除数量}
        """
        matcher = CardMatcher(self.session)
        result = await matcher.update_card_item_relations(card_id, user_id, item_ids)
        await self.session.commit()
        return result

    async def get_card_item_ids(self, card_id: int, user_id: int | None) -> List[str]:
        """获取卡券关联的商品ID列表
        
        Args:
            card_id: 卡券ID
            
        Returns:
            商品ID列表
        """
        matcher = CardMatcher(self.session)
        return await matcher.get_card_item_ids(card_id, user_id)
