"""商品管理及卡券选商品页面的查询索引自检。"""
from __future__ import annotations

from common.db.query_indexes import ensure_query_indexes
from common.models.xy_catalog_item import XYCatalogItem

ITEM_QUERY_INDEX_NAMES = (
    "idx_cat_created_id",
    "idx_cat_account_created_id",
    "idx_cat_owner_created",
    "idx_item_id",
)


async def ensure_item_query_indexes(conn) -> None:
    """使用启动自检的 DDL 连接补齐缺失的商品查询索引。"""
    await ensure_query_indexes(conn, XYCatalogItem.__table__, ITEM_QUERY_INDEX_NAMES, label="商品查询")
