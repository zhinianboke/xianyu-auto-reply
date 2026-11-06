"""Regression tests for sold-order detail hydration; all API data is synthetic."""
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

from multidict import CIMultiDict
from sqlalchemy import Integer, MetaData, Text, select
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from common.models.card import Card
from common.models.card_item_relation import CardItemRelation
from common.models.xy_order import XYOrder
from common.services.card_matcher import CardMatcher
from common.services.order_service import OrderService


def sold_item(order_no="test-order"):
    return {
        "commonData": {
            "orderId": order_no,
            "orderStatus": "待发货",
            "itemId": "test-item",
        },
        "buyerInfoVO": {"buyerId": "test-buyer"},
        "priceVO": {"totalPrice": "12.34", "buyNum": "1"},
    }


def sold_page(items, cookies_str="test-cookie=initial", next_page=False):
    return {
        "items": items,
        "total_count": len(items),
        "next_page": next_page,
        "cookies_str": cookies_str,
    }


def detail_response(spec_value="测试规格-1"):
    return {
        "ret": ["SUCCESS::调用成功"],
        "data": {
            "components": [{
                "render": "orderInfoVO",
                "data": {"itemInfo": {
                    "itemId": "test-item",
                    "skuInfo": f" 套餐 : {spec_value} ",
                    "price": "1.23",
                    "buyAmount": "2",
                }},
            }],
        },
    }


class OrderSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.account = SimpleNamespace(
            account_id="test-account", owner_id=1, cookie="test-cookie=initial"
        )
        self.session = MagicMock(spec=AsyncSession)
        self.session.execute.return_value = MagicMock()
        self.session.execute.return_value.scalars.return_value.all.return_value = []
        self.service = OrderService(self.session)
        self.service._fetch_sold_orders_page = AsyncMock(
            return_value=sold_page([sold_item()])
        )
        self.service._upsert_order = AsyncMock(return_value="inserted")
        self.detail_class = self.enterContext(patch(
            "common.services.order_service.OrderDetailService"
        ))
        self.detail_class.return_value.cookies_str = self.account.cookie
        self.hydrate = AsyncMock(return_value=True)
        self.detail_class.return_value.fetch_and_update_order_detail = self.hydrate

    def existing_order(self, spec_name=None, spec_value=None):
        order = SimpleNamespace(
            order_no="test-order", spec_name=spec_name, spec_value=spec_value
        )
        self.session.execute.return_value.scalars.return_value.all.return_value = [order]
        self.service._upsert_order.return_value = "skipped"

    async def test_new_orders_are_hydrated_for_both_queries(self):
        for query in ("ALL", "NOT_SHIP"):
            with self.subTest(query=query):
                self.hydrate.reset_mock()
                result = await self.service._fetch_xianyu_orders_impl(self.account, query)
                self.hydrate.assert_awaited_once_with(
                    "test-order", item_id="test-item", buyer_id="test-buyer"
                )
                self.assertEqual(result["new_inserted"], 1)
                self.assertEqual(result["failed"], 0)

    async def test_pending_orders_with_either_missing_spec_are_hydrated(self):
        for name, value in ((None, None), ("套餐", ""), ("", "测试规格-1")):
            with self.subTest(name=name, value=value):
                self.existing_order(name, value)
                self.hydrate.reset_mock()
                result = await self.service._fetch_xianyu_orders_impl(self.account, "NOT_SHIP")
                self.hydrate.assert_awaited_once()
                self.assertEqual(result["total_fetched"], 1)
                self.assertEqual(result["new_inserted"], 0)

    async def test_complete_existing_specs_do_not_request_details(self):
        self.existing_order("套餐", "测试规格-1")
        await self.service._fetch_xianyu_orders_impl(self.account, "NOT_SHIP")
        self.detail_class.assert_not_called()

    async def test_all_query_does_not_backfill_existing_orders(self):
        self.existing_order()
        await self.service._fetch_xianyu_orders_impl(self.account, "ALL")
        self.detail_class.assert_not_called()

    async def test_detail_failure_does_not_fail_list_sync(self):
        self.service._fetch_sold_orders_page.return_value = sold_page([
            sold_item("test-order-1"), sold_item("test-order-2")
        ])
        self.hydrate.side_effect = [False, True]
        result = await self.service._fetch_xianyu_orders_impl(self.account)
        self.assertEqual(self.hydrate.await_count, 2)
        self.assertEqual(result, {
            "total_fetched": 2, "new_inserted": 2,
            "updated": 0, "failed": 0, "errors": [],
        })
        self.session.rollback.assert_not_awaited()

    async def test_cookie_refresh_flows_between_details_and_pages(self):
        first = sold_page([sold_item("test-order-1"), sold_item("test-order-2")],
                          "test-cookie=page-1", next_page=True)
        first["total_count"] = 31
        second = sold_page([sold_item("test-order-3")], "test-cookie=page-2")
        self.service._fetch_sold_orders_page.side_effect = [first, second]
        services = []

        def make_detail(account_id, cookies_str):
            detail = SimpleNamespace(cookies_str=cookies_str)

            async def hydrate(*args, **kwargs):
                detail.cookies_str = f"test-cookie=detail-{len(services)}"
                return True

            detail.fetch_and_update_order_detail = AsyncMock(side_effect=hydrate)
            services.append(detail)
            return detail

        self.detail_class.side_effect = make_detail
        with patch("common.services.order_service.asyncio.sleep", new_callable=AsyncMock):
            await self.service._fetch_xianyu_orders_impl(self.account)
        self.assertEqual(self.detail_class.call_args_list, [
            call("test-account", "test-cookie=page-1"),
            call("test-account", "test-cookie=detail-1"),
            call("test-account", "test-cookie=page-2"),
        ])
        self.assertEqual(
            self.service._fetch_sold_orders_page.call_args_list[1].args,
            ("test-cookie=detail-2", 2),
        )


class OrderSyncIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        db_path = Path(self.temp_dir.name, "orders.sqlite").as_posix()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        self.addAsyncCleanup(self.engine.dispose)
        metadata = MetaData()
        for model in (XYOrder, Card, CardItemRelation):
            table = model.__table__.to_metadata(metadata)
            # SQLite requires INTEGER for auto-increment and TEXT for MySQL LONGTEXT.
            table.c.id.type = Integer()
            for column in table.c:
                if isinstance(column.type, LONGTEXT):
                    column.type = Text()
        async with self.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        # Replace the DB factory before the detail service imports production configuration.
        db_module = ModuleType("common.db.session")
        db_module.async_session_maker = self.sessions
        self.enterContext(patch.dict(sys.modules, {"common.db.session": db_module}))
        self.account = SimpleNamespace(
            account_id="test-account", owner_id=1, cookie="test-cookie=initial"
        )
        self.response = MagicMock()
        self.response.headers = CIMultiDict()
        self.response.__aenter__.return_value = self.response
        self.response.json = AsyncMock(return_value=detail_response())
        http = MagicMock()
        http.__aenter__.return_value = http
        http.post.return_value = self.response
        self.enterContext(patch("aiohttp.ClientSession", return_value=http))
        self.enterContext(patch(
            "common.services.order_service.get_goofish_connector", return_value=MagicMock()
        ))
        self.enterContext(patch(
            "common.services.order_service.asyncio.sleep", new_callable=AsyncMock
        ))

    async def sync(self, items, query="ALL"):
        async with self.sessions() as session:
            service = OrderService(session)
            with patch.object(service, "_fetch_sold_orders_page", new_callable=AsyncMock) as fetch:
                fetch.return_value = sold_page(items)
                return await service._fetch_xianyu_orders_impl(self.account, query)

    async def test_six_specs_are_persisted_and_match_unique_cards(self):
        values = [f"测试规格-{index}" for index in range(1, 7)]
        async with self.sessions() as session:
            for index, value in enumerate(values, start=1):
                session.add(Card(
                    id=index, user_id=1, name=value, type="text", enabled=True,
                    is_multi_spec=True, spec_name="套餐", spec_value=value,
                ))
                session.add(CardItemRelation(
                    id=index, user_id=1, card_id=index, item_id="test-item"
                ))
            await session.commit()
        self.response.json.side_effect = [detail_response(value) for value in values]
        result = await self.sync([sold_item(f"test-order-{i}") for i in range(1, 7)])
        self.assertEqual(result["new_inserted"], 6)
        self.assertEqual(result["failed"], 0)
        async with self.sessions() as session:
            orders = (await session.execute(select(XYOrder).order_by(XYOrder.order_no))).scalars().all()
            self.assertEqual(len(orders), 6)
            for index, order in enumerate(orders, start=1):
                self.assertEqual((order.spec_name, order.spec_value), ("套餐", values[index - 1]))
                self.assertEqual(order.amount, Decimal("1.23"))
                self.assertEqual(order.quantity, 2)
                cards = await CardMatcher(session).get_cards_by_item_id(
                    order.item_id, order.spec_name, order.spec_value
                )
                self.assertEqual([card["id"] for card in cards], [index])

    async def test_api_failure_keeps_base_orders_and_pending_sync_recovers(self):
        items = [sold_item("test-order-1"), sold_item("test-order-2")]
        self.response.json.side_effect = [
            {"ret": ["FAIL::temporary failure"]}, detail_response("测试规格-2")
        ]
        result = await self.sync(items)
        self.assertEqual(result["new_inserted"], 2)
        self.assertEqual(result["failed"], 0)
        async with self.sessions() as session:
            orders = (await session.execute(select(XYOrder).order_by(XYOrder.order_no))).scalars().all()
            self.assertEqual(len(orders), 2)
            self.assertIsNone(orders[0].spec_name)
            self.assertEqual(orders[0].amount, Decimal("12.34"))
            self.assertEqual(orders[1].spec_value, "测试规格-2")
        self.response.json.side_effect = None
        self.response.json.return_value = detail_response()
        self.response.json.reset_mock()
        result = await self.sync(items, "NOT_SHIP")
        self.assertEqual(result["failed"], 0)
        self.response.json.assert_awaited_once()
        async with self.sessions() as session:
            order = (await session.execute(select(XYOrder).where(
                XYOrder.order_no == "test-order-1"
            ))).scalar_one()
            self.assertEqual((order.spec_name, order.spec_value), ("套餐", "测试规格-1"))
        self.response.json.reset_mock()
        await self.sync(items, "NOT_SHIP")
        self.response.json.assert_not_awaited()

    async def test_http_exception_does_not_stop_subsequent_orders(self):
        self.response.json.side_effect = [
            RuntimeError("simulated transport failure"),
            RuntimeError("simulated transport failure"),
            RuntimeError("simulated transport failure"),
            detail_response("测试规格-2"),
        ]
        result = await self.sync([sold_item("test-order-1"), sold_item("test-order-2")])
        self.assertEqual(result["new_inserted"], 2)
        self.assertEqual(result["failed"], 0)
        async with self.sessions() as session:
            orders = (await session.execute(select(XYOrder).order_by(XYOrder.order_no))).scalars().all()
            self.assertEqual(len(orders), 2)
            self.assertIsNone(orders[0].spec_value)
            self.assertEqual(orders[1].spec_value, "测试规格-2")


if __name__ == "__main__":
    unittest.main()
