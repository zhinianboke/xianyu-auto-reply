"""卡券创建、更新及软删除服务，写入前验证完整请求的对象权限。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from loguru import logger
from sqlalchemy import select

from common.models.card import Card
from common.services.card_access import CardAccess
from common.services.card_matcher import CardMatcher
from common.db.query_conditions import not_deleted


class CardMutationMixin:
    """提供卡券写入方法，由 CardService 统一持有数据库会话。"""

    async def check_card_duplicate(
        self,
        user_id: int,
        item_id: Optional[str],
        name: str,
        is_multi_spec: bool,
        spec_name: Optional[str] = None,
        spec_value: Optional[str] = None,
        exclude_card_id: Optional[int] = None,
    ) -> Optional[str]:
        """检查卡券是否重复
        
        Args:
            user_id: 用户ID
            item_id: 商品ID
            name: 卡券名称
            is_multi_spec: 是否多规格
            spec_name: 规格名称
            spec_value: 规格值
            exclude_card_id: 排除的卡券ID（用于更新时排除自身）
            
        Returns:
            重复时返回错误信息，不重复返回None
        """
        if is_multi_spec:
            # 多规格卡券：检查同一商品下 name + spec_name + spec_value 组合是否重复
            stmt = select(Card).where(
                Card.user_id == user_id,
                not_deleted(Card),
                Card.item_id == item_id,
                Card.name == name,
                Card.is_multi_spec == True,
                Card.spec_name == spec_name,
                Card.spec_value == spec_value,
            )
        else:
            # 普通卡券：检查同一商品下 name 是否重复
            stmt = select(Card).where(
                Card.user_id == user_id,
                not_deleted(Card),
                Card.item_id == item_id,
                Card.name == name,
                Card.is_multi_spec == False,
            )
        
        # 更新时排除自身
        if exclude_card_id:
            stmt = stmt.where(Card.id != exclude_card_id)
        
        result = await self.session.execute(stmt)
        existing = result.scalars().first()
        
        if existing:
            if is_multi_spec:
                return f"同一商品下已存在相同名称和规格的卡券：{name}（{spec_name}: {spec_value}）"
            else:
                return f"同一商品下已存在相同名称的卡券：{name}"
        
        return None

    async def create_card(
        self,
        user_id: int,
        name: str,
        card_type: str,
        item_id: Optional[str] = None,
        api_config: Optional[Dict] = None,
        text_content: Optional[str] = None,
        data_content: Optional[str] = None,
        image_url: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
        description: Optional[str] = None,
        enabled: bool = True,
        delay_seconds: int = 0,
        use_no_logistics_form: bool = False,
        price: Optional[str] = None,
        is_dockable: bool = False,
        fee_payer: Optional[str] = None,
        min_price: Optional[str] = None,
        dock_visibility: Optional[str] = None,
        is_multi_spec: bool = False,
        spec_name: Optional[str] = None,
        spec_value: Optional[str] = None,
    ) -> int:
        """创建卡券
        
        Raises:
            ValueError: 卡券重复时抛出
        """
        if item_id:
            item_id = (await CardAccess(self.session).require_items([item_id], user_id))[0]

        # 检查重复
        duplicate_msg = await self.check_card_duplicate(
            user_id=user_id,
            item_id=item_id,
            name=name,
            is_multi_spec=is_multi_spec,
            spec_name=spec_name,
            spec_value=spec_value,
        )
        if duplicate_msg:
            raise ValueError(duplicate_msg)

        if use_no_logistics_form and card_type != "text":
            raise ValueError("无需邮寄表单发货仅支持固定文字卡券")
        
        card = Card(
            user_id=user_id,
            item_id=item_id,
            name=name,
            type=card_type,
            api_config=json.dumps(api_config) if api_config else None,
            text_content=text_content,
            data_content=data_content,
            image_url=image_url,
            image_urls=json.dumps(image_urls) if image_urls else None,
            description=description,
            enabled=enabled,
            delay_seconds=delay_seconds,
            use_no_logistics_form=use_no_logistics_form,
            price=price,
            is_dockable=is_dockable,
            fee_payer=fee_payer,
            min_price=min_price,
            dock_visibility=dock_visibility,
            is_multi_spec=is_multi_spec,
            spec_name=spec_name,
            spec_value=spec_value,
        )
        self.session.add(card)
        await self.session.commit()
        await self.session.refresh(card)
        return card.id

    async def update_card(
        self,
        card_id: int,
        user_id: int,
        **kwargs
    ) -> bool:
        """更新卡券
        
        Raises:
            ValueError: 卡券重复时抛出
        """
        card = (await CardAccess(self.session).require_cards([card_id], user_id, lock=True))[0]

        # 获取更新后的值（如果没有传入则使用原值）
        new_name = kwargs.get("name", card.name)
        new_item_id = kwargs.get("item_id", card.item_id)
        new_is_multi_spec = kwargs.get("is_multi_spec", card.is_multi_spec)
        new_spec_name = kwargs.get("spec_name", card.spec_name)
        new_spec_value = kwargs.get("spec_value", card.spec_value)
        new_type = kwargs.get("type", card.type)
        new_use_no_logistics_form = kwargs.get(
            "use_no_logistics_form", card.use_no_logistics_form
        )

        if new_use_no_logistics_form and new_type != "text":
            raise ValueError("无需邮寄表单发货仅支持固定文字卡券")

        # 多商品关联会清空旧 item_id；只改内容/开关不能把既有合法卡券误判为重名。
        # 历史 NULL 与 False 都表示普通卡，网页按 False 回传不算切换规格类型。
        current_identity = (
            card.name, card.item_id, bool(card.is_multi_spec), card.spec_name, card.spec_value,
        )
        new_identity = (
            new_name, new_item_id, bool(new_is_multi_spec), new_spec_name, new_spec_value,
        )
        if new_identity != current_identity:
            duplicate_msg = await self.check_card_duplicate(
                user_id=user_id,
                item_id=new_item_id,
                name=new_name,
                is_multi_spec=new_is_multi_spec,
                spec_name=new_spec_name,
                spec_value=new_spec_value,
                exclude_card_id=card_id,
            )
            if duplicate_msg:
                raise ValueError(duplicate_msg)

        if "item_id" in kwargs:
            # 旧客户端显式修改单商品绑定时同步关联表；只改内容不能覆盖已有多商品绑定。
            # 商品授权在公共关联方法中一次性校验，不能无条件用旧 item_id 作为保留证明。
            await CardMatcher(self.session).update_card_item_relations(
                card_id, user_id, [new_item_id] if new_item_id else [],
            )

        for key, value in kwargs.items():
            if hasattr(card, key):
                if key == "api_config" and isinstance(value, dict):
                    value = json.dumps(value)
                elif key == "image_urls" and isinstance(value, list):
                    value = json.dumps(value)
                setattr(card, key, value)

        await self.session.commit()
        return True

    async def delete_card(self, card_id: int, user_id: int) -> bool:
        """校验归属后软删除一张卡券及其关联；参数为卡券、用户ID，返回是否成功。"""
        await self.batch_delete_cards([card_id], user_id)
        return True

    async def batch_delete_cards(self, card_ids: List[int], user_id: int) -> int:
        """先整组验证并锁定自有卡券，再软删除；返回实际删除数量，无权限时整组拒绝。"""
        cards = await CardAccess(self.session).require_cards(card_ids, user_id, lock=True)
        matcher = CardMatcher(self.session)
        for card in cards:
            rel_count = await matcher.delete_relations_by_card_id(card.id, user_id)
            card.is_deleted = True
            card.enabled = False
            logger.info(f"软删除卡券 {card.id} 及其 {rel_count} 条关联记录，用户 {user_id}")
        await self.session.commit()
        return len(cards)

    async def batch_save_and_bind(
        self,
        user_id: int,
        item_ids: List[str],
        name: str,
        card_type: str,
        api_config: Optional[Dict] = None,
        text_content: Optional[str] = None,
        data_content: Optional[str] = None,
        image_url: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
        description: Optional[str] = None,
        enabled: bool = True,
        delay_seconds: int = 0,
        use_no_logistics_form: bool = False,
        price: Optional[str] = None,
        is_dockable: bool = False,
        fee_payer: Optional[str] = None,
        min_price: Optional[str] = None,
        dock_visibility: Optional[str] = None,
        is_multi_spec: bool = False,
        spec_name: Optional[str] = None,
        spec_value: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建一个卡券并通过关联表绑定到多个商品（替代旧的复制卡券逻辑）
        
        Args:
            user_id: 用户ID
            item_ids: 商品ID列表
            其他参数: 卡券配置
            
        Returns:
            {"card_id": 新建卡券ID, "bindCount": 绑定商品数}
        """
        if use_no_logistics_form and card_type != "text":
            raise ValueError("无需邮寄表单发货仅支持固定文字卡券")

        # 整组商品授权先于创建卡券，避免批量请求部分成功留下数据。
        item_ids = await CardAccess(self.session).require_items(item_ids, user_id)

        # 1. 创建卡券（不设置 item_id，因为走关联表）
        card = Card(
            user_id=user_id,
            item_id=None,
            name=name,
            type=card_type,
            api_config=json.dumps(api_config) if api_config else None,
            text_content=text_content,
            data_content=data_content,
            image_url=image_url,
            image_urls=json.dumps(image_urls) if image_urls else None,
            description=description,
            enabled=enabled,
            delay_seconds=delay_seconds,
            use_no_logistics_form=use_no_logistics_form,
            price=price,
            is_dockable=is_dockable,
            fee_payer=fee_payer,
            min_price=min_price,
            dock_visibility=dock_visibility,
            is_multi_spec=is_multi_spec,
            spec_name=spec_name,
            spec_value=spec_value,
        )
        self.session.add(card)
        await self.session.flush()  # 获取 card.id
        
        # 2. 通过关联表绑定到多个商品
        matcher = CardMatcher(self.session)
        bind_result = await matcher.batch_bind_cards_to_items(
            user_id=user_id,
            card_ids=[card.id],
            item_ids=item_ids,
        )
        
        await self.session.commit()
        return {
            "card_id": card.id,
            "bind_count": bind_result["success_count"],
        }
