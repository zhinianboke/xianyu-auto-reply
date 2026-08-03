import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


def _function_source(path: Path, class_name: str, function_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == function_name:
                    return ast.get_source_segment(source, child) or ""
    raise AssertionError(f"未找到 {class_name}.{function_name}")


class OrderAccountIsolationTest(unittest.TestCase):
    def test_order_writes_require_and_filter_account_id(self):
        path = ROOT / "common/services/order_service.py"
        for name in (
            "update_order_chat_id",
            "update_order_delivery_fail_reason",
            "update_order_delivery_info",
            "record_delivery_for_closed_order",
            "update_order_status",
        ):
            source = _function_source(path, "OrderService", name)
            self.assertIn("account_id", source)
            self.assertIn("XYOrder.account_id == account_id", source)

    def test_scheduler_blocks_self_buyer_orders(self):
        source = _function_source(
            ROOT / "scheduler/app/services/scheduler/redelivery_task.py",
            "RedeliveryTask",
            "_get_pending_orders",
        )
        self.assertIn("XYOrder.buyer_id != str(account.unb)", source)

    def test_session_failures_use_cooldown_instead_of_persisted_placeholder(self):
        source = (ROOT / "scheduler/app/services/scheduler/redelivery_task.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("clear_order_chat_id", source)
        self.assertIn("'创建会话'", source)
        self.assertNotIn("placeholder_chat_id", source)

    def test_delivery_request_and_lookup_are_account_scoped(self):
        path = ROOT / "websocket/app/api/routes/internal.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("class DeliverOrderRequest", source)
        self.assertIn("    account_id: str", source)
        self.assertIn(
            "db_manager.get_order_by_id(request.order_no, request.account_id)",
            source,
        )

    def test_order_page_actions_and_delivery_logs_are_account_scoped(self):
        order_route = (ROOT / "backend-web/app/api/routes/orders.py").read_text(
            encoding="utf-8"
        )
        frontend_api = (ROOT / "frontend/src/api/orders.ts").read_text(encoding="utf-8")
        chat_page = (ROOT / "frontend/src/pages/chat-new/ChatNew.tsx").read_text(
            encoding="utf-8"
        )
        order_service = (ROOT / "common/services/order_service.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("account_id: str", order_route)
        self.assertIn("get_order_by_no(request.order_no, request.account_id)", order_route)
        self.assertIn("account_id=${encodeURIComponent(accountId)}", frontend_api)
        self.assertIn("manualDelivery(orderNo, activeAccountId)", chat_page)
        self.assertIn("group_by(XYAutoReplyMessageLog.account_id, XYAutoReplyMessageLog.order_no)", order_service)
