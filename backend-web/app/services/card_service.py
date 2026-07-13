"""卡券服务"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select, delete, func, or_, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, load_only
from loguru import logger

from common.models.card import Card
from common.services.card_matcher import CardMatcher
from common.utils.response_field import extract_card_api_response_content


from common.utils.time_utils import safe_isoformat
class CardService:
    """卡券服务类"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_cards(self, user_id: int | None) -> List[Dict[str, Any]]:
        """获取卡券列表
        
        Args:
            user_id: 用户ID，None表示查询所有用户（管理员）
        """
        stmt = select(Card)
        if user_id is not None:
            stmt = stmt.where(Card.user_id == user_id)
        result = await self.session.execute(stmt)
        cards = result.scalars().all()
        return [self._card_to_dict_simple(card) for card in cards]

    # 轻量模式只需查询的列（剔除 text_content/data_content/api_config/image_urls
    # 等大字段，避免一次性返回全部卡券时传输/读取超大内容）
    _LITE_COLUMNS = (
        Card.id, Card.user_id, Card.item_id, Card.name, Card.type,
        Card.enabled, Card.delay_seconds, Card.delivery_count, Card.price,
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
        base_conditions = []
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
        from common.models.dock_record import DockRecord

        base_conditions = [Card.is_dockable == True, Card.enabled == True]
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
            from common.models.dock_code_binding import DockCodeBinding
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
        stmt = select(Card).options(selectinload(Card.item_relations)).where(Card.id == card_id)
        if user_id is not None:
            stmt = stmt.where(Card.user_id == user_id)
        result = await self.session.execute(stmt)
        card = result.scalars().first()
        return self._card_to_dict(card) if card else None

    async def get_cards_by_item_id(self, user_id: int | None, item_id: str) -> List[Dict[str, Any]]:
        """获取指定商品关联的所有卡券列表（管理展示用，不过滤启用状态和规格）
        
        Args:
            user_id: 用户ID，None表示查询所有用户（管理员）
            item_id: 商品ID
        """
        matcher = CardMatcher(self.session)
        return await matcher.get_all_cards_by_item_id(item_id)

    async def get_cards_by_item_id_and_spec(
        self,
        item_id: str,
        spec_name: Optional[str] = None,
        spec_value: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """根据商品ID和规格获取卡券列表（用于发货匹配，委托给CardMatcher）
        
        Args:
            item_id: 商品ID
            spec_name: 规格名称（可选）
            spec_value: 规格值（可选）
            
        Returns:
            匹配的卡券列表
        """
        matcher = CardMatcher(self.session)
        return await matcher.get_cards_by_item_id(item_id, spec_name, spec_value)

    async def batch_clear_item_relations(self, item_ids: List[str]) -> int:
        """批量清空商品的卡券关联关系（不删除卡券本身）
        
        Args:
            item_ids: 商品ID列表
            
        Returns:
            删除的关联记录总数
        """
        matcher = CardMatcher(self.session)
        removed = await matcher.batch_delete_relations_by_item_ids(item_ids)
        await self.session.commit()
        return removed

    async def delete_card_item_relation(self, card_id: int, item_id: str) -> bool:
        """删除指定卡券与指定商品的关联关系
        
        Args:
            card_id: 卡券ID
            item_id: 商品ID
            
        Returns:
            是否成功删除
        """
        matcher = CardMatcher(self.session)
        success = await matcher.delete_relation_by_card_and_item(card_id, item_id)
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

    async def consume_batch_data(self, card_id: int) -> Optional[str]:
        """消费批量数据卡券的一条数据

        从卡券的 data_content 中取出第一行数据并删除。

        并发安全设计（CAS 乐观锁，不依赖行锁与事务隔离级别）：
            采用「读取当前内容 → 用单条 UPDATE 原子替换」的比较并交换方式：
            ``UPDATE xy_cards SET data_content=<去掉首行后的剩余内容>
              WHERE id=:card_id AND data_content=<读取到的旧内容>``。
            MySQL（InnoDB）保证对同一行的单条 UPDATE 串行执行，并发的多个消费
            请求中只有一个能匹配旧内容并成功（rowcount=1），其余 rowcount=0 后
            自动重读重试，从根本上避免同一条卡密被重复派发。

        Args:
            card_id: 卡券ID

        Returns:
            消费的数据内容或None
        """
        # CAS 失败（被其他并发请求抢先消费）时的最大重试次数，避免极端竞争下死循环
        max_cas_retries = 50

        for _ in range(max_cas_retries):
            # 1. 读取当前卡券内容
            stmt = select(Card.data_content).where(Card.id == card_id)
            result = await self.session.execute(stmt)
            current_content = result.scalar_one_or_none()

            if current_content is None:
                logger.warning(f"卡券 {card_id} 不存在或没有批量数据")
                return None

            # 2. 计算首行与剩余内容
            lines = [line.strip() for line in current_content.split('\n') if line.strip()]
            if not lines:
                logger.warning(f"卡券 {card_id} 批量数据已用完")
                return None

            consumed_data = lines[0]
            remaining_lines = lines[1:]
            new_content = '\n'.join(remaining_lines) if remaining_lines else ''

            # 3. CAS 原子替换：仅当 data_content 仍等于刚读取到的旧值时才更新
            cas_stmt = (
                update(Card)
                .where(Card.id == card_id, Card.data_content == current_content)
                .values(data_content=new_content)
            )
            cas_result = await self.session.execute(cas_stmt)
            await self.session.commit()

            if cas_result.rowcount == 1:
                logger.info(f"卡券 {card_id} 消费数据成功，剩余 {len(remaining_lines)} 条")
                return consumed_data

            # rowcount=0：内容已被其他并发请求改写，重读重试
            logger.warning(f"卡券 {card_id} 消费存在并发竞争，重试中...")

        logger.error(f"卡券 {card_id} 消费失败：并发竞争超过最大重试次数 {max_cas_retries}")
        return None

    async def increment_delivery_count(self, card_id: int) -> bool:
        """增加卡券的发货次数
        
        Args:
            card_id: 卡券ID
            
        Returns:
            是否更新成功
        """
        stmt = select(Card).where(Card.id == card_id)
        result = await self.session.execute(stmt)
        card = result.scalars().first()
        
        if not card:
            return False
        
        card.delivery_count = (card.delivery_count or 0) + 1
        await self.session.commit()
        return True

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
        stmt = select(Card).where(Card.id == card_id, Card.user_id == user_id)
        result = await self.session.execute(stmt)
        card = result.scalars().first()
        if not card:
            return False

        # 获取更新后的值（如果没有传入则使用原值）
        new_name = kwargs.get("name", card.name)
        new_item_id = kwargs.get("item_id", card.item_id)
        new_is_multi_spec = kwargs.get("is_multi_spec", card.is_multi_spec)
        new_spec_name = kwargs.get("spec_name", card.spec_name)
        new_spec_value = kwargs.get("spec_value", card.spec_value)

        # 检查重复（排除自身）
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
        """删除卡券（同时删除关联表记录）"""
        # 先删除关联表记录
        matcher = CardMatcher(self.session)
        rel_count = await matcher.delete_relations_by_card_id(card_id)
        if rel_count > 0:
            logger.info(f"删除卡券 {card_id} 的 {rel_count} 条关联记录")
        
        stmt = delete(Card).where(Card.id == card_id, Card.user_id == user_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def batch_delete_cards(self, card_ids: List[int], user_id: int) -> int:
        """批量删除卡券（同时删除关联表记录）"""
        # 先批量删除关联表记录
        matcher = CardMatcher(self.session)
        for card_id in card_ids:
            rel_count = await matcher.delete_relations_by_card_id(card_id)
            if rel_count > 0:
                logger.info(f"删除卡券 {card_id} 的 {rel_count} 条关联记录")
        
        stmt = delete(Card).where(Card.id.in_(card_ids), Card.user_id == user_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

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

    async def get_card_item_ids(self, card_id: int) -> List[str]:
        """获取卡券关联的商品ID列表
        
        Args:
            card_id: 卡券ID
            
        Returns:
            商品ID列表
        """
        matcher = CardMatcher(self.session)
        return await matcher.get_card_item_ids(card_id)

    def _card_to_dict(self, card: Card) -> Dict[str, Any]:
        """将卡券对象转换为字典（包含关联商品，需要预加载item_relations）"""
        api_config = None
        if card.api_config:
            try:
                api_config = json.loads(card.api_config)
            except json.JSONDecodeError:
                api_config = card.api_config

        image_urls = None
        if card.image_urls:
            try:
                image_urls = json.loads(card.image_urls)
            except json.JSONDecodeError:
                image_urls = None

        return {
            "id": card.id,
            "user_id": card.user_id,
            "item_id": card.item_id,
            "name": card.name,
            "type": card.type,
            "description": card.description,
            "enabled": card.enabled,
            "delay_seconds": card.delay_seconds,
            "delivery_count": card.delivery_count,
            "price": card.price,
            "is_dockable": card.is_dockable,
            "fee_payer": card.fee_payer,
            "min_price": card.min_price,
            "dock_visibility": card.dock_visibility,
            "is_multi_spec": card.is_multi_spec,
            "spec_name": card.spec_name,
            "spec_value": card.spec_value,
            "api_config": api_config,
            "text_content": card.text_content,
            "data_content": card.data_content,
            "image_url": card.image_url,
            "image_urls": image_urls,
            "created_at": safe_isoformat(card.created_at),
            "updated_at": safe_isoformat(card.updated_at),
            "item_ids": [r.item_id for r in card.item_relations] if hasattr(card, 'item_relations') and card.item_relations else [],
        }

    def _card_to_dict_lite(self, card: Card) -> Dict[str, Any]:
        """将卡券对象转换为轻量字典（仅列表/选择场景所需字段）。

        刻意剔除 text_content / data_content / api_config / image_urls 等大字段，
        用于「商品关联卡券」选择弹窗等需要一次性拉取全部卡券的场景，避免传输
        超大 JSON 拖慢界面。需要完整内容时请调用 get_card_by_id 按需获取。
        """
        return {
            "id": card.id,
            "user_id": card.user_id,
            "item_id": card.item_id,
            "name": card.name,
            "type": card.type,
            "enabled": card.enabled,
            "delay_seconds": card.delay_seconds,
            "delivery_count": card.delivery_count,
            "price": card.price,
            "is_dockable": card.is_dockable,
            "fee_payer": card.fee_payer,
            "min_price": card.min_price,
            "dock_visibility": card.dock_visibility,
            "is_multi_spec": card.is_multi_spec,
            "spec_name": card.spec_name,
            "spec_value": card.spec_value,
            "created_at": safe_isoformat(card.created_at),
            "updated_at": safe_isoformat(card.updated_at),
        }

    def _card_to_dict_simple(self, card: Card) -> Dict[str, Any]:
        """将卡券对象转换为字典（不查询关联表，用于列表展示）"""
        api_config = None
        if card.api_config:
            try:
                api_config = json.loads(card.api_config)
            except json.JSONDecodeError:
                api_config = card.api_config

        image_urls = None
        if card.image_urls:
            try:
                image_urls = json.loads(card.image_urls)
            except json.JSONDecodeError:
                image_urls = None

        return {
            "id": card.id,
            "user_id": card.user_id,
            "item_id": card.item_id,
            "name": card.name,
            "type": card.type,
            "description": card.description,
            "enabled": card.enabled,
            "delay_seconds": card.delay_seconds,
            "delivery_count": card.delivery_count,
            "price": card.price,
            "is_dockable": card.is_dockable,
            "fee_payer": card.fee_payer,
            "min_price": card.min_price,
            "dock_visibility": card.dock_visibility,
            "is_multi_spec": card.is_multi_spec,
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


    async def get_available_card(
        self,
        account_pk: int,
        item_id: Optional[str] = None,
    ) -> Optional[Card]:
        """获取可用卡券
        
        Args:
            account_pk: 账号主键
            item_id: 商品ID（可选，用于匹配多规格卡券）
            
        Returns:
            可用的卡券或None
        """
        try:
            from common.models.xy_account import XYAccount
            
            # 获取账号信息
            account_stmt = select(XYAccount).where(XYAccount.id == account_pk)
            account_result = await self.session.execute(account_stmt)
            account = account_result.scalars().first()
            
            if not account:
                return None
            
            # 查找启用的卡券
            stmt = select(Card).where(
                Card.user_id == account.owner_id,
                Card.enabled == True,
            )
            
            # 如果有商品ID，优先匹配多规格卡券
            if item_id:
                spec_stmt = stmt.where(
                    Card.is_multi_spec == True,
                    Card.spec_value == item_id,
                )
                spec_result = await self.session.execute(spec_stmt)
                spec_card = spec_result.scalars().first()
                if spec_card:
                    return spec_card
            
            # 返回第一个可用的卡券
            stmt = stmt.order_by(Card.created_at.asc()).limit(1)
            result = await self.session.execute(stmt)
            return result.scalars().first()
            
        except Exception as e:
            logger.error(f"获取可用卡券失败: {e}")
            return None

    async def mark_card_used(self, card_id: int, order_no: Optional[str] = None) -> bool:
        """标记卡券已使用
        
        对于数据类型卡券，可能需要从data_content中移除已使用的内容
        
        Args:
            card_id: 卡券ID
            order_no: 订单号（可选）
            
        Returns:
            是否成功
        """
        try:
            stmt = select(Card).where(Card.id == card_id)
            result = await self.session.execute(stmt)
            card = result.scalars().first()
            
            if not card:
                return False
            
            # 对于数据类型卡券，移除第一行数据
            if card.type == "data" and card.data_content:
                lines = card.data_content.strip().split("\n")
                if len(lines) > 1:
                    card.data_content = "\n".join(lines[1:])
                else:
                    # 数据用完，禁用卡券
                    card.data_content = ""
                    card.enabled = False
                
                await self.session.commit()
            
            logger.info(f"卡券 {card_id} 已标记使用，订单: {order_no}")
            return True
            
        except Exception as e:
            logger.error(f"标记卡券使用失败: {e}")
            await self.session.rollback()
            return False

    async def get_card_content(self, card_id: int) -> Optional[str]:
        """获取卡券内容
        
        根据卡券类型返回相应的内容
        
        Args:
            card_id: 卡券ID
            
        Returns:
            卡券内容或None
        """
        try:
            stmt = select(Card).where(Card.id == card_id)
            result = await self.session.execute(stmt)
            card = result.scalars().first()
            
            if not card or not card.enabled:
                return None
            
            if card.type == "text":
                return card.text_content
            elif card.type == "data":
                # 返回第一行数据
                if card.data_content:
                    lines = card.data_content.strip().split("\n")
                    return lines[0] if lines else None
            elif card.type == "image":
                return card.image_url
            elif card.type == "api":
                # API类型需要调用外部接口
                return await self._call_card_api(card)
            
            return None
            
        except Exception as e:
            logger.error(f"获取卡券内容失败: {e}")
            return None

    async def _call_card_api(self, card: Card) -> Optional[str]:
        """调用卡券API获取内容
        
        参数:
            card: 卡券对象
            
        返回:
            API返回的内容或None
        """
        try:
            import httpx
            
            if not card.api_config:
                return None
            
            config = json.loads(card.api_config) if isinstance(card.api_config, str) else card.api_config
            
            url = config.get("url")
            method = config.get("method", "GET").upper()
            headers = config.get("headers", {})
            params = config.get("params", {})
            body = config.get("body", {})
            
            if not url:
                return None
            
            async with httpx.AsyncClient(timeout=30) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers, params=params)
                else:
                    response = await client.post(url, headers=headers, json=body)
                
                response.raise_for_status()
                response_field = config.get("response_field") or config.get("responseField")
                return extract_card_api_response_content(response.text, response_field)
                    
        except Exception as e:
            logger.error(f"调用卡券API失败: {e}")
            return None
