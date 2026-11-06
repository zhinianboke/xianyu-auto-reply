"""
卡券可选商品服务

功能：
1. 为「卡券关联商品」选择弹窗提供轻量数据：已关联商品详情、全部匹配商品项
2. 仅返回选择场景所需的轻字段（item_id / title / price），避免一次性拉取
   全部商品的重字段（metadata、默认回复状态、卡券状态等）导致界面卡顿
3. 待选列表独立分页，搜索与全选都只匹配商品 ID / 标题，不查询详情和配置状态
"""
from __future__ import annotations

from time import perf_counter
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.retry import with_db_retry
from common.models.card_item_relation import CardItemRelation
from common.models.xy_catalog_item import XYCatalogItem


class SelectableItemService:
    """卡券可选商品服务（轻量查询）"""

    def __init__(self, session: AsyncSession):
        """保存请求级数据库会话；参数为 AsyncSession，无返回值。"""
        self.session = session

    @staticmethod
    def _item_to_light(item_id: str, title: Optional[str], price: Optional[str]) -> Dict[str, Any]:
        """商品 → 选择项轻量字典"""
        return {"item_id": item_id, "title": title, "price": price}

    @staticmethod
    def _conditions(owner_id: Optional[int], search: str) -> list:
        """构建分页与全选共用筛选；参数为用户和关键词，返回 SQL 条件列表。"""
        conditions = []
        if owner_id is not None:
            conditions.append(XYCatalogItem.owner_id == owner_id)
        keyword = search.strip()
        if keyword:
            conditions.append(or_(
                XYCatalogItem.item_id.contains(keyword, autoescape=True),
                XYCatalogItem.title.contains(keyword, autoescape=True),
            ))
        return conditions

    @with_db_retry(max_retries=2)
    async def get_page(
        self, owner_id: Optional[int], page: int = 1,
        page_size: int = 20, search: str = "",
    ) -> Dict[str, Any]:
        """查询待选商品轻量页。

        Args:
            owner_id: 用户作用域，None 为管理员；page/page_size 为分页，search 为名称或 ID。
        Returns:
            轻量 list、精确 total、page、page_size、total_pages 和 has_more。
            总数按商品记录统计；同一标识跨账号的记录在前端合并，不影响翻页终止条件。
        """
        started = perf_counter()
        conditions = self._conditions(owner_id, search)
        try:
            total = (await self.session.execute(
                select(func.count(XYCatalogItem.id)).where(*conditions)
            )).scalar_one()
            items = []
            if total and (page - 1) * page_size < total:
                rows = await self.session.execute(
                    select(XYCatalogItem.item_id, XYCatalogItem.title, XYCatalogItem.price)
                    .where(*conditions)
                    .order_by(XYCatalogItem.created_at.desc(), XYCatalogItem.id.desc())
                    .offset((page - 1) * page_size).limit(page_size)
                )
                items = [self._item_to_light(*row) for row in rows.all()]
            logger.info(
                "待选商品查询完成: owner_id={}, page={}, page_size={}, keyword={}, "
                "total={}, returned={}, duration_ms={:.1f}",
                owner_id, page, page_size, search, total, len(items),
                (perf_counter() - started) * 1000,
            )
            return {
                "list": items, "total": total, "page": page, "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
                "has_more": page * page_size < total,
            }
        except Exception:
            await self.session.rollback()
            logger.exception("待选商品查询失败: owner_id={}, page={}, keyword={}",
                             owner_id, page, search)
            raise

    async def get_associated_items(
        self,
        card_id: int,
        owner_id: Optional[int],
    ) -> List[Dict[str, Any]]:
        """获取卡券已关联商品的轻量详情（用于弹窗右侧「已选商品」展示）

        关联表先去重商品标识后 JOIN 商品表，避免多来源关联放大查询结果；
        同一 item_id 可能对应多条商品记录
        （同一商品挂在不同账号下），按 item_id 去重保留其一。已删除商品（无商品
        记录）不在此返回，但选中态由 get_card_item_ids 单独提供，保存时不丢失。

        Args:
            card_id: 卡券ID
            owner_id: 用户ID，None 表示管理员（不加 owner 过滤）
        """
        relation_ids = select(CardItemRelation.item_id).where(
            CardItemRelation.card_id == card_id
        ).distinct().subquery("associated_item_ids")
        stmt = (
            select(XYCatalogItem.item_id, XYCatalogItem.title, XYCatalogItem.price)
            .join(relation_ids, relation_ids.c.item_id == XYCatalogItem.item_id)
            .order_by(XYCatalogItem.created_at.desc(), XYCatalogItem.id.desc())
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
        conditions = self._conditions(owner_id, search)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(XYCatalogItem.created_at.desc(), XYCatalogItem.id.desc())
        rows = await self.session.execute(stmt)

        seen: set[str] = set()
        items: List[Dict[str, Any]] = []
        for item_id, title, price in rows.all():
            if item_id in seen:
                continue
            seen.add(item_id)
            items.append(self._item_to_light(item_id, title, price))
        return items
