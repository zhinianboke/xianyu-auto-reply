"""
卡券可选商品服务

功能：
1. 为「卡券关联商品」选择弹窗提供轻量数据：已关联商品详情、全部匹配商品项
2. 仅返回选择场景所需的轻字段（item_id / title / price），避免一次性拉取
   全部商品的重字段（metadata、默认回复状态、卡券状态等）导致界面卡顿
3. 左侧待选列表复用现有 item_service.list_items_paginated（真分页 + 关键字搜索），
   本服务只补齐右侧「已选商品详情」与「全选筛选结果」两个轻量查询
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.card_item_relation import CardItemRelation
from common.models.xy_catalog_item import XYCatalogItem


class SelectableItemService:
    """卡券可选商品服务（轻量查询）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _item_to_light(item_id: str, title: Optional[str], price: Optional[str]) -> Dict[str, Any]:
        """商品 → 选择项轻量字典"""
        return {"item_id": item_id, "title": title, "price": price}

    async def get_associated_items(
        self,
        card_id: int,
        owner_id: Optional[int],
    ) -> List[Dict[str, Any]]:
        """获取卡券已关联商品的轻量详情（用于弹窗右侧「已选商品」展示）

        通过关联表 join 商品表取 title/price；同一 item_id 可能对应多条商品记录
        （同一商品挂在不同账号下），按 item_id 去重保留其一。已删除商品（无商品
        记录）不在此返回，但选中态由 get_card_item_ids 单独提供，保存时不丢失。

        Args:
            card_id: 卡券ID
            owner_id: 用户ID，None 表示管理员（不加 owner 过滤）
        """
        stmt = (
            select(XYCatalogItem.item_id, XYCatalogItem.title, XYCatalogItem.price)
            .join(CardItemRelation, CardItemRelation.item_id == XYCatalogItem.item_id)
            .where(CardItemRelation.card_id == card_id)
        )
        if owner_id is not None:
            stmt = stmt.where(XYCatalogItem.owner_id == owner_id)
        rows = await self.session.execute(stmt)

        seen: set[str] = set()
        items: List[Dict[str, Any]] = []
        for item_id, title, price in rows.all():
            if item_id in seen:
                continue
            seen.add(item_id)
            items.append(self._item_to_light(item_id, title, price))
        return items

    async def get_all_selectable_item_keys(
        self,
        owner_id: Optional[int],
        search: str = "",
    ) -> List[Dict[str, Any]]:
        """获取全部匹配的可选商品轻量项（供「全选当前筛选结果」使用，不分页）

        搜索匹配 商品ID / 标题，仅在用户主动点「全选」时触发。
        """
        stmt = select(XYCatalogItem.item_id, XYCatalogItem.title, XYCatalogItem.price)
        conditions = []
        if owner_id is not None:
            conditions.append(XYCatalogItem.owner_id == owner_id)
        if search and search.strip():
            kw = f"%{search.strip()}%"
            conditions.append(
                or_(
                    cast(XYCatalogItem.item_id, String).ilike(kw),
                    XYCatalogItem.title.ilike(kw),
                )
            )
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(XYCatalogItem.created_at.desc())
        rows = await self.session.execute(stmt)

        seen: set[str] = set()
        items: List[Dict[str, Any]] = []
        for item_id, title, price in rows.all():
            if item_id in seen:
                continue
            seen.add(item_id)
            items.append(self._item_to_light(item_id, title, price))
        return items
