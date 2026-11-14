"""商品管理分页查询：先定位本页商品，再在同一次查询中读取配置状态。

保留商品 ID、标题、完整详情包含搜索以及历史卡券状态口径，减少数据库往返。
"""
from __future__ import annotations

from time import perf_counter

from loguru import logger
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.retry import with_db_retry
from common.models.card import Card
from common.models.card_item_relation import CardItemRelation
from common.models.default_reply import DefaultReply
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem


class ItemQueryService:
    """商品管理专用查询，复用请求会话，不创建独立连接池。"""

    def __init__(self, session: AsyncSession):
        """保存请求会话；参数为 AsyncSession，无返回值。"""
        self.session = session

    @staticmethod
    def _conditions(owner_id, account_id, keyword, is_polished,
                    is_multi_spec, multi_quantity_delivery) -> list:
        """构建原有筛选条件；参数为用户、账号、关键词和状态，返回 SQL 表达式列表。"""
        conditions = []
        if owner_id is not None:
            conditions.append(XYCatalogItem.owner_id == owner_id)
        if account_id:
            # 唯一账号标识转换为主键，商品查询和计数都无需 JOIN 账号表。
            account_pk = select(XYAccount.id).where(
                XYAccount.account_id == account_id
            ).scalar_subquery()
            conditions.append(XYCatalogItem.account_pk == account_pk)
        if keyword and keyword.strip():
            pattern = f"%{keyword.strip()}%"
            conditions.append(or_(
                XYCatalogItem.item_id.like(pattern),
                XYCatalogItem.title.like(pattern),
                cast(XYCatalogItem.metadata_json, String).like(pattern),
            ))
        if is_polished is not None:
            conditions.append(XYCatalogItem.is_polished == is_polished)
        for key, value in (
            ("is_multi_spec", is_multi_spec),
            ("multi_quantity_delivery", multi_quantity_delivery),
        ):
            if value is None:
                continue
            field = XYCatalogItem.metadata_json[key]
            conditions.append(field.as_boolean() == value if value else or_(
                XYCatalogItem.metadata_json.is_(None),
                field.as_boolean() == False,
                field.is_(None),
            ))
        return conditions

    @staticmethod
    def _page_statement(conditions: list, page: int, page_size: int):
        """按筛选和分页构造查询，返回商品、账号、默认回复状态和卡券状态。"""
        # 派生表先分页，详情读取和状态子查询只对本页执行；时间相同按主键稳定排序。
        page_ids = (
            select(XYCatalogItem.id).where(*conditions)
            .order_by(XYCatalogItem.created_at.desc(), XYCatalogItem.id.desc())
            .offset((page - 1) * page_size).limit(page_size).subquery("page_items")
        )
        reply_conditions = (
            DefaultReply.account_id == XYAccount.account_id,
            DefaultReply.item_id == XYCatalogItem.item_id,
        )
        reply_enabled = (
            select(DefaultReply.enabled).where(*reply_conditions)
            .order_by(DefaultReply.id.desc()).limit(1)
            .correlate(XYCatalogItem, XYAccount).scalar_subquery()
        )
        has_reply = select(DefaultReply.id).where(*reply_conditions).correlate(
            XYCatalogItem, XYAccount
        ).exists()
        # 保留现有口径：关联表存在，或旧字段中存在启用卡券，即为已配置。
        has_relation = select(CardItemRelation.id).where(
            CardItemRelation.item_id == XYCatalogItem.item_id
        ).correlate(XYCatalogItem).exists()
        has_legacy_card = select(Card.id).where(
            Card.item_id == XYCatalogItem.item_id, Card.enabled == True
        ).correlate(XYCatalogItem).exists()
        return (
            select(XYCatalogItem, XYAccount.account_id,
                   func.coalesce(reply_enabled, False), has_reply,
                   or_(has_relation, has_legacy_card))
            .join(page_ids, page_ids.c.id == XYCatalogItem.id)
            .outerjoin(XYAccount, XYCatalogItem.account_pk == XYAccount.id)
            .order_by(XYCatalogItem.created_at.desc(), XYCatalogItem.id.desc())
        )

    @with_db_retry(max_retries=2)
    async def get_page(
        self, owner_id: int | None, account_id: str | None = None,
        page: int = 1, page_size: int = 20, keyword: str | None = None,
        is_polished: bool | None = None, is_multi_spec: bool | None = None,
        multi_quantity_delivery: bool | None = None,
    ) -> tuple[list, int]:
        """获取真实分页数据。

        Args:
            owner_id: 用户作用域，None 为管理员；其余参数为账号、分页及原有筛选条件。
        Returns:
            (商品及配置状态行列表, 精确总数)，保留孤儿账号商品。
        """
        started = perf_counter()
        conditions = self._conditions(owner_id, account_id, keyword, is_polished,
                                      is_multi_spec, multi_quantity_delivery)
        try:
            count = select(func.count(XYCatalogItem.id)).where(*conditions)
            total = (await self.session.execute(count)).scalar_one()
            rows = []
            if total and (page - 1) * page_size < total:
                result = await self.session.execute(
                    self._page_statement(conditions, page, page_size)
                )
                rows = result.all()
            logger.info(
                "商品分页查询完成: owner_id={}, account_id={}, page={}, page_size={}, "
                "keyword={}, total={}, returned={}, duration_ms={:.1f}",
                owner_id, account_id, page, page_size, keyword, total, len(rows),
                (perf_counter() - started) * 1000,
            )
            return rows, total
        except Exception:
            # 连接失败后先回滚，让重试重新获取健康连接，不能复用失败事务。
            await self.session.rollback()
            logger.exception("商品分页查询失败: owner_id={}, account_id={}, page={}",
                             owner_id, account_id, page)
            raise
