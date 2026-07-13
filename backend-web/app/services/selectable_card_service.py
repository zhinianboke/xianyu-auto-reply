"""
商品可选卡券服务

功能：
1. 为「商品关联卡券」选择弹窗提供服务端合并分页：自有卡券 + 对接卡券
2. 两个来源（xy_cards / xy_dock_records）拼接后统一分页、统一搜索、去重
3. 仅返回列表/选择所需的轻字段（不含卡密/文本/API配置/图片等大字段），
   避免卡券过多时一次性传输超大内容导致界面卡顿

拼接分页策略：结果视为 [自有卡券... , 对接卡券...] 的逻辑连续序列，
按各来源总数与请求偏移量决定当前页从哪个来源取多少条，确定性强，
避免对两张结构不同的表做 UNION。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, load_only

from common.models.card import Card
from common.models.dock_record import DockRecord


class SelectableCardService:
    """商品可选卡券服务（自有 + 对接 合并分页）"""

    # 自有卡券轻量模式只需查询的列（避免读取 LONGTEXT 等大字段）
    _OWN_LITE_COLUMNS = (
        Card.id, Card.name, Card.type, Card.is_multi_spec,
        Card.spec_name, Card.spec_value, Card.enabled, Card.price,
    )

    def __init__(self, session: AsyncSession):
        self.session = session

    # ---------- 查询条件构建 ----------

    def _own_conditions(self, user_id: Optional[int], search: str) -> List[Any]:
        """构建自有卡券查询条件（owner 作用域 + 搜索：名称/类型/ID）"""
        conds: List[Any] = []
        if user_id is not None:
            conds.append(Card.user_id == user_id)
        if search:
            kw = f"%{search}%"
            conds.append(
                or_(
                    Card.name.ilike(kw),
                    Card.description.ilike(kw),
                    Card.type.ilike(kw),
                    cast(Card.id, String).ilike(kw),
                )
            )
        return conds

    def _dock_conditions(self, user_id: Optional[int], search: str) -> List[Any]:
        """构建对接卡券查询条件

        - 仅启用（status=True）的对接记录
        - owner 作用域
        - 去重：card_id 不在本人自有卡券集合内（与前端历史行为一致）
        - 搜索：对接名称 或 卡券名称
        """
        conds: List[Any] = [DockRecord.status == True]  # noqa: E712
        if user_id is not None:
            conds.append(DockRecord.user_id == user_id)
        # 去重：对接记录引用的 card_id 若已是本人自有卡券，则不重复展示
        own_ids_subq = select(Card.id)
        if user_id is not None:
            own_ids_subq = own_ids_subq.where(Card.user_id == user_id)
        conds.append(DockRecord.card_id.notin_(own_ids_subq))
        if search:
            kw = f"%{search}%"
            conds.append(or_(DockRecord.dock_name.ilike(kw), Card.name.ilike(kw)))
        return conds

    # ---------- 语句构建 ----------

    def _own_data_stmt(self, own_conds: List[Any], offset: int, limit: int):
        """自有卡券分页数据语句（仅查询轻量列）"""
        stmt = (
            select(Card)
            .where(*own_conds)
            .order_by(Card.id.desc())
            .options(load_only(*self._OWN_LITE_COLUMNS))
            .offset(offset)
            .limit(limit)
        )
        return stmt

    def _dock_data_stmt(self, dock_conds: List[Any], offset: int, limit: Optional[int]):
        """对接卡券分页数据语句

        JOIN 卡券表获取名称/价格/规格；自关联上级记录获取 sub_dock_price
        （二级记录对接价显示上级设置的下级价格）。limit=None 表示不分页取全部。
        """
        parent_dock = aliased(DockRecord)
        stmt = (
            select(
                DockRecord,
                Card.name.label("card_name"),
                Card.price.label("card_price"),
                Card.is_multi_spec.label("card_is_multi_spec"),
                Card.spec_name.label("card_spec_name"),
                Card.spec_value.label("card_spec_value"),
                parent_dock.sub_dock_price.label("parent_sub_dock_price"),
            )
            .outerjoin(Card, DockRecord.card_id == Card.id)
            .outerjoin(parent_dock, DockRecord.parent_dock_id == parent_dock.id)
            .where(*dock_conds)
            .order_by(DockRecord.id.desc())
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return stmt

    # ---------- 行 → 统一项 ----------

    def _own_card_to_item(self, card: Card) -> Dict[str, Any]:
        """自有卡券 → 选择项字典"""
        return {
            "id": card.id,
            "name": card.name,
            "type": card.type,
            "source": "own",
            "dock_name": None,
            "dock_record_id": None,
            "is_multi_spec": card.is_multi_spec,
            "spec_name": card.spec_name,
            "spec_value": card.spec_value,
            "enabled": card.enabled,
            "price": card.price,
            "unique_key": f"own_{card.id}",
        }

    def _dock_row_to_item(self, row: Any) -> Dict[str, Any]:
        """对接记录行 → 选择项字典"""
        record: DockRecord = row[0]
        parent_sub = row.parent_sub_dock_price
        # 二级记录对接价显示上级设置的下级价格，否则用卡券价格
        display_price = parent_sub if (record.level == 2 and parent_sub) else row.card_price
        source = "dock_l2" if record.level == 2 else "dock_l1"
        return {
            "id": record.card_id,
            "name": row.card_name or record.dock_name,
            "type": "api",
            "source": source,
            "dock_name": record.dock_name,
            "dock_record_id": record.id,
            "is_multi_spec": row.card_is_multi_spec,
            "spec_name": row.card_spec_name,
            "spec_value": row.card_spec_value,
            "enabled": record.status,
            "price": display_price,
            "unique_key": f"dock_{record.id}",
        }

    # ---------- 对外方法 ----------

    async def get_selectable_cards_paginated(
        self,
        item_id: str,
        user_id: Optional[int],
        page: int = 1,
        page_size: int = 50,
        search: str = "",
    ) -> Dict[str, Any]:
        """合并分页获取商品的可选卡券（自有在前、对接在后）

        Args:
            item_id: 商品ID（保留参数，便于后续按商品维度扩展；当前不参与过滤）
            user_id: 用户ID，None 表示管理员（不加 owner 过滤）
            page: 页码（从1开始）
            page_size: 每页数量
            search: 搜索关键词

        Returns:
            统一分页结构 {list, total, page, page_size, total_pages}
        """
        own_conds = self._own_conditions(user_id, search)
        dock_conds = self._dock_conditions(user_id, search)

        # 各来源总数
        own_count_stmt = select(func.count(Card.id))
        if own_conds:
            own_count_stmt = own_count_stmt.where(*own_conds)
        own_total = (await self.session.execute(own_count_stmt)).scalar() or 0

        # 对接计数需 JOIN 卡券表（搜索条件可能引用 Card.name）
        dock_count_stmt = (
            select(func.count(DockRecord.id))
            .outerjoin(Card, DockRecord.card_id == Card.id)
            .where(*dock_conds)
        )
        dock_total = (await self.session.execute(dock_count_stmt)).scalar() or 0

        total = own_total + dock_total
        offset = (page - 1) * page_size
        items: List[Dict[str, Any]] = []

        if offset < own_total:
            # 本页起点落在自有卡券区间
            own_limit = min(page_size, own_total - offset)
            own_rows = (await self.session.execute(
                self._own_data_stmt(own_conds, offset, own_limit)
            )).scalars().all()
            items.extend(self._own_card_to_item(c) for c in own_rows)
            # 自有不足一页，用对接卡券从头补齐剩余名额
            remaining = page_size - len(items)
            if remaining > 0:
                dock_rows = (await self.session.execute(
                    self._dock_data_stmt(dock_conds, 0, remaining)
                )).all()
                items.extend(self._dock_row_to_item(r) for r in dock_rows)
        else:
            # 本页完全落在对接卡券区间
            dock_offset = offset - own_total
            dock_rows = (await self.session.execute(
                self._dock_data_stmt(dock_conds, dock_offset, page_size)
            )).all()
            items.extend(self._dock_row_to_item(r) for r in dock_rows)

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        return {
            "list": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def get_all_selectable_card_keys(
        self,
        user_id: Optional[int],
        search: str = "",
    ) -> List[Dict[str, Any]]:
        """获取全部匹配的可选卡券轻量项（供「全选当前筛选结果」使用，不分页）

        仅返回轻字段，不含卡密/文本等大内容；仅在用户主动点「全选」时触发。
        """
        own_conds = self._own_conditions(user_id, search)
        dock_conds = self._dock_conditions(user_id, search)

        own_rows = (await self.session.execute(
            select(Card)
            .where(*own_conds)
            .order_by(Card.id.desc())
            .options(load_only(*self._OWN_LITE_COLUMNS))
        )).scalars().all()
        items: List[Dict[str, Any]] = [self._own_card_to_item(c) for c in own_rows]

        dock_rows = (await self.session.execute(
            self._dock_data_stmt(dock_conds, 0, None)
        )).all()
        items.extend(self._dock_row_to_item(r) for r in dock_rows)
        return items
