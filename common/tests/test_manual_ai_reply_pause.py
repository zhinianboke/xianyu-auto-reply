"""人工回复 AI 精确暂停的源码契约回归测试。"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


def _function_source(path: Path, class_name: str, function_name: str) -> str:
    source = path.read_text(encoding="utf-8-sig")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == function_name:
                    return ast.get_source_segment(source, child) or ""
    raise AssertionError(f"未找到 {class_name}.{function_name}")


class ManualAiReplyPauseTest(unittest.TestCase):
    def test_pause_key_includes_account_buyer_and_item(self):
        source = _function_source(
            ROOT / "websocket/app/services/xianyu/resource_manager.py",
            "AutoReplyPauseManager",
            "pause_ai_reply_for_manual_message",
        )
        self.assertIn("self.buyer_contexts.get", source)
        self.assertIn("self.paused_ai_contexts[(cookie_id, buyer_id, target_item_id)]", source)
        self.assertIn("target_item_id = str(item_id or remembered_item_id).strip()", source)

    def test_ai_only_pause_is_configurable_and_checked_before_sending(self):
        schema = (ROOT / "common/schemas/ai_reply.py").read_text(encoding="utf-8")
        auto_reply = (ROOT / "websocket/app/services/xianyu/auto_reply_service.py").read_text(encoding="utf-8")
        ai_engine = (ROOT / "websocket/app/services/xianyu/ai_reply_engine.py").read_text(encoding="utf-8")
        frontend = (ROOT / "frontend/src/pages/accounts/Accounts.tsx").read_text(encoding="utf-8")

        self.assertIn("manual_reply_ai_pause_enabled", schema)
        self.assertIn("manual_reply_ai_pause_minutes", schema)
        self.assertIn("get_remaining_ai_pause_time", auto_reply)
        self.assertIn("is_ai_reply_paused(cookie_id, user_id, item_id)", ai_engine)
        self.assertIn("人工回复后暂停 AI", frontend)

    def test_paused_ai_reply_is_recorded_as_a_dedicated_log(self):
        auto_reply = (ROOT / "websocket/app/services/xianyu/auto_reply_service.py").read_text(encoding="utf-8")
        frontend = (ROOT / "frontend/src/pages/autoReplyLogs/AutoReplyLogs.tsx").read_text(encoding="utf-8")

        self.assertIn("_record_manual_reply_ai_paused_log", auto_reply)
        self.assertIn('\"reply_strategy\": \"ai\"', auto_reply)
        self.assertIn('\"matched_rule_type\": \"ai\"', auto_reply)
        self.assertIn('\"send_status\": \"paused\"', auto_reply)
        self.assertIn(
            'f\"暂停ai回复{pause_minutes}分钟，预计恢复时间：{pause_end_time}\"',
            auto_reply,
        )
        self.assertIn("paused: '暂停回复'", frontend)


if __name__ == "__main__":
    unittest.main()
