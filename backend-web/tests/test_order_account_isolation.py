from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from common.services.order_service import OrderService


class CatalogRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class CatalogSession:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        return CatalogRows(self.rows)


class EmptyOrderListResult:
    def scalar(self):
        return 0

    def scalars(self):
        return self

    def all(self):
        return []


class OrderListSession:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        return EmptyOrderListResult()


class OrderAccountIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_order_list_hides_known_foreign_account_items(self):
        session = OrderListSession()
        service = OrderService(session)

        orders, total, _ = await service.list_orders(
            owner_id=1,
            account_id="鹰眼",
        )

        self.assertEqual(orders, [])
        self.assertEqual(total, 0)
        self.assertTrue(
            any(
                "xy_catalog_items.account_id = xy_accounts.id"
                in statement
                and "xy_accounts.account_id = xy_orders.account_id"
                in statement
                for statement in session.statements
            )
        )

    async def test_known_foreign_item_is_not_written_to_current_account(self):
        session = CatalogSession([("item-owned-by-yaoyao", 3)])
        service = OrderService(session)
        service._fetch_sold_orders_page = AsyncMock(
            return_value={
                "items": [
                    {
                        "commonData": {
                            "orderId": "order-1",
                            "orderStatus": "订单待发货",
                            "itemId": "item-owned-by-yaoyao",
                        },
                        "buyerInfoVO": {},
                        "priceVO": {},
                        "rightVO": {},
                    }
                ],
                "next_page": False,
                "total_count": 1,
            }
        )
        service._upsert_order = AsyncMock()

        result = await service._fetch_xianyu_orders_impl(
            SimpleNamespace(
                id=4,
                account_id="鹰眼",
                owner_id=1,
                cookie="cookie",
            )
        )

        self.assertEqual(result["total_fetched"], 0)
        self.assertEqual(result["failed"], 1)
        service._upsert_order.assert_not_awaited()
        self.assertTrue(
            any("xy_catalog_items.owner_id" in statement for statement in session.statements)
        )
