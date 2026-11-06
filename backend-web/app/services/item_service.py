"""
商品服务

功能：
1. 商品目录CRUD操作
2. 商品信息更新（标题、价格、描述等）
3. 商品列表查询
4. 批量删除商品
5. 抓取闲鱼商品并入库（带账号级并发锁）

公共读写实现位于 common 目录；网页分页使用独立查询服务减少数据库往返，
其余方法继承公共实现，scheduler 使用公共服务保持兼容。
"""
from common.services.item_query_service import ItemQueryService
from common.services.item_service import ItemService as CommonItemService


class ItemService(CommonItemService):
    """网页商品服务：公共读写逻辑保持兼容，分页使用优化查询。"""

    async def list_items_paginated(
        self, owner_id: int | None, account_id: str | None = None,
        page: int = 1, page_size: int = 20, keyword: str | None = None,
        is_polished: bool | None = None, is_multi_spec: bool | None = None,
        multi_quantity_delivery: bool | None = None,
    ) -> tuple[list[dict], int]:
        """查询商品页；参数与公共服务相同，返回兼容原接口的商品列表和精确总数。"""
        rows, total = await ItemQueryService(self.session).get_page(
            owner_id, account_id, page, page_size, keyword, is_polished,
            is_multi_spec, multi_quantity_delivery,
        )
        return [
            self._serialize_item(item, account, {
                "enabled": bool(enabled), "has_config": bool(has_reply),
            }, bool(has_card))
            for item, account, enabled, has_reply, has_card in rows
        ], total

__all__ = ["ItemService"]
