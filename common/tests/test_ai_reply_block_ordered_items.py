"""已下单商品禁止 AI 回复的源码契约回归测试。"""
from __future__ import annotations

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


class AiReplyBlockOrderedItemsTest(unittest.TestCase):
    def test_ordered_item_check_matches_account_buyer_and_current_item(self):
        source = _function_source(
            ROOT / "websocket/app/services/xianyu/auto_reply_service.py",
            "AutoReplyService",
            "_check_user_has_order_for_item",
        )
        self.assertIn("XYOrder.account_id == self.cookie_id", source)
        self.assertIn("XYOrder.buyer_id == buyer_id", source)
        self.assertIn("XYOrder.item_id == normalized_item_id", source)
        self.assertIn("if not buyer_id or not normalized_item_id", source)

    def test_feature_is_an_account_switch_with_indexed_order_lookup(self):
        account_model = (ROOT / "common/models/xy_account.py").read_text(encoding="utf-8")
        order_model = (ROOT / "common/models/xy_order.py").read_text(encoding="utf-8")
        account_route = (ROOT / "backend-web/app/api/routes/cookies.py").read_text(encoding="utf-8")
        reply_source = _function_source(
            ROOT / "websocket/app/services/xianyu/auto_reply_service.py",
            "AutoReplyService",
            "get_ai_reply",
        )

        self.assertIn("ai_reply_block_ordered_items", account_model)
        self.assertIn('Index("idx_order_account_buyer_item", "account_id", "buyer_id", "item_id")', order_model)
        self.assertIn('"/{account_id}/ai-reply-block-ordered-items"', account_route)
        self.assertLess(
            reply_source.index("if account.ai_reply_block_ordered_items"),
            reply_source.index("ai_engine = get_ai_reply_engine()"),
        )


if __name__ == "__main__":
    unittest.main()
