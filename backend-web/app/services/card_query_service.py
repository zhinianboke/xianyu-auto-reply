"""卡券列表、详情和公开对接列表查询，排除已软删除的卡券。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload, load_only

from common.models.card import Card
from common.models.dock_record import DockRecord
from common.models.dock_code_binding import DockCodeBinding
from common.services.card_matcher import CardMatcher
from common.utils.time_utils import safe_isoformat
from common.db.query_conditions import not_deleted


class CardQueryMixin:
    """提供卡券查询方法，由 CardService 统一持有数据库会话。"""

    async def get_all_cards(self, user_id: int | None) -> List[Dict[str, Any]]:
        """获取卡券列表
        
        Args:
            user_id: 用户ID，None表示查询所有用户（管理员）
        """
        stmt = select(Card).where(not_deleted(Card))
        if user_id is not None:
            stmt = stmt.where(Card.user_id == user_id)
        result = await self.session.execute(stmt)
        cards = result.scalars().all()
        return [self._card_to_dict_simple(card) for card in cards]

    # 轻量模式只需查询的列（剔除 text_content/data_content/api_config/image_urls
    # 等大字段，避免一次性返回全部卡券时传输/读取超大内容）
    _LITE_COLUMNS = (
        Card.id, Card.user_id, Card.item_id, Card.name, Card.type,
        Card.enabled, Card.delay_seconds, Card.use_no_logistics_form,
        Card.delivery_count, Card.price,
        Card.is_dockable, Card.fee_payer, Card.min_price, Card.dock_visibility,
        Card.is_multi_spec, Card.spec_name, Card.spec_value,
        Card.created_at, Card.updated_at,
    )

    async def get_cards_paginated(
        self,
        user_id: int | None,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
        card_type: str = "",
        lite: bool = False,
    ) -> Dict[str, Any]:
        """分页获取卡券列表

        Args:
            user_id: 用户ID，None表示查询所有用户（管理员）
            page: 页码（从1开始）
            page_size: 每页数量
            search: 搜索关键词（匹配名称或描述）
            card_type: 卡券类型过滤（api/text/data/image）
            lite: 轻量模式。为 True 时仅返回列表/选择场景所需的轻字段，
                剔除 text_content/data_content/api_config/image_urls 等大字段，
                用于「商品关联卡券」等需要一次性拉取全部卡券的场景，显著减小
                响应体与数据库读取量。完整内容请调用 get_card_by_id 按需获取。

        Returns:
            包含分页数据的字典：{list, total, page, page_size, total_pages}
        """
        # 构建基础查询条件
        base_conditions = [not_deleted(Card)]
        if user_id is not None:
            base_conditions.append(Card.user_id == user_id)
        if search:
            base_conditions.append(
                or_(
                    Card.name.ilike(f"%{search}%"),
                    Card.description.ilike(f"%{search}%"),
                )
            )
        if card_type:
            base_conditions.append(Card.type == card_type)
        
        # 查询总数
        count_stmt = select(func.count(Card.id))
        if base_conditions:
            count_stmt = count_stmt.where(*base_conditions)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # 查询分页数据
        offset = (page - 1) * page_size
        data_stmt = select(Card).order_by(Card.id.desc()).offset(offset).limit(page_size)
        if base_conditions:
            data_stmt = data_stmt.where(*base_conditions)
        # 轻量模式只查询必要列，避免读取 LONGTEXT 等大字段
        if lite:
            data_stmt = data_stmt.options(load_only(*self._LITE_COLUMNS))
        result = await self.session.execute(data_stmt)
        cards = result.scalars().all()

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        to_dict = self._card_to_dict_lite if lite else self._card_to_dict_simple
        return {
            "list": [to_dict(card) for card in cards],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def get_dockable_cards_paginated(
        self,
        current_user_id: int,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
        card_type: str = "",
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        """分页获取所有可对接卡券（跨用户，仅展示公开信息）
        
        Args:
            current_user_id: 当前用户ID，用于判断是否已对接
            page: 页码（从1开始）
            page_size: 每页数量
            search: 搜索关键词（匹配名称或描述）
            card_type: 卡券类型过滤
            
        Returns:
            包含分页数据的字典
        """
        base_conditions = [not_deleted(Card), Card.is_dockable == True, Card.enabled == True]
        if search:
            base_conditions.append(
                or_(
                    Card.name.ilike(f"%{search}%"),
                    Card.description.ilike(f"%{search}%"),
                )
            )
        if card_type:
            base_conditions.append(Card.type == card_type)

        # dock_visibility 过滤：管理员不受限制，普通用户按可见性过滤
        if not is_admin:
            # 查出当前用户通过对接码绑定的供应商ID列表
            binding_stmt = (
                select(DockCodeBinding.target_user_id)
                .where(DockCodeBinding.user_id == current_user_id)
            )
            binding_result = await self.session.execute(binding_stmt)
            bound_owner_ids = [row[0] for row in binding_result.all()]

            # 可见条件：public 的所有人可见，dealer_only 的仅已绑定对接码的供应商卡券可见
            if bound_owner_ids:
                visibility_condition = or_(
                    Card.dock_visibility == None,
                    Card.dock_visibility == 'public',
                    and_(Card.dock_visibility == 'dealer_only', Card.user_id.in_(bound_owner_ids)),
                )
            else:
                visibility_condition = or_(
                    Card.dock_visibility == None,
                    Card.dock_visibility == 'public',
                )
            base_conditions.append(visibility_condition)

        # 查询总数
        count_stmt = select(func.count(Card.id)).where(*base_conditions)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # 查询分页数据
        offset = (page - 1) * page_size
        data_stmt = (
            select(Card)
            .where(*base_conditions)
            .order_by(Card.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(data_stmt)
        cards = result.scalars().all()

        # 查询当前用户对这些卡券的对接记录（card_id -> dock_record_id）
        card_ids = [c.id for c in cards]
        docked_map: Dict[int, int] = {}
        if card_ids:
            dock_stmt = select(DockRecord.card_id, DockRecord.id).where(
                DockRecord.user_id == current_user_id,
                DockRecord.card_id.in_(card_ids),
                DockRecord.level == 1,
            )
            dock_result = await self.session.execute(dock_stmt)
            for row in dock_result.all():
                docked_map[row[0]] = row[1]
        
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        
        return {
            "list": [self._dockable_card_to_dict(card, docked_map) for card in cards],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def _dockable_card_to_dict(self, card: Card, docked_map: Dict[int, int] | None = None) -> Dict[str, Any]:
        """将可对接卡券转换为公开信息字典（不暴露敏感内容）"""
        dock_record_id = docked_map.get(card.id) if docked_map else None
        return {
            "id": card.id,
            "user_id": card.user_id,
            "name": card.name,
            "type": card.type,
            "description": card.description,
            "price": card.price,
            "fee_payer": card.fee_payer,
            "min_price": card.min_price,
            "is_multi_spec": card.is_multi_spec,
            "spec_name": card.spec_name,
            "spec_value": card.spec_value,
            "is_docked": dock_record_id is not None,
            "dock_record_id": dock_record_id,
            "created_at": safe_isoformat(card.created_at),
        }

    async def get_card_by_id(self, card_id: int, user_id: int | None) -> Optional[Dict[str, Any]]:
        """获取单个卡券
        
        Args:
            card_id: 卡券ID
            user_id: 用户ID，None表示不限制用户（管理员）
        """
        stmt = select(Card).options(selectinload(Card.item_relations)).where(
            Card.id == card_id, not_deleted(Card)
        )
        if user_id is not None:
            stmt = stmt.where(Card.user_id == user_id)
        result = await self.session.execute(stmt)
        card = result.scalars().first()
        if not card:
            return None
        data = self._card_to_dict(card)
        # 供货方详情不泄露分销商商品列表；管理员保留全量关联读取。
        data["item_ids"] = await CardMatcher(self.session).get_card_item_ids(card_id, user_id)
        return data
