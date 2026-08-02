from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from common.services.order_service import OrderService


class OrderAccountIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cookie_identity_mismatch_skips_order_sync(self):
        service = OrderService(SimpleNamespace())
        service._fetch_xianyu_orders_impl = AsyncMock()

        result = await service.fetch_xianyu_orders(
            SimpleNamespace(
                account_id="瑶瑶",
                unb="1857495265",
                cookie="unb=2222129819336",
            )
        )

        self.assertEqual(result["total_fetched"], 0)
        self.assertIn("实际身份", result["errors"][0])
        service._fetch_xianyu_orders_impl.assert_not_awaited()
