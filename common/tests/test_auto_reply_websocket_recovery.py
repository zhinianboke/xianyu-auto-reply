"""自动回复常驻 WebSocket 重连的源码契约回归测试。"""
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


class AutoReplyWebSocketRecoveryTest(unittest.TestCase):
    def test_normal_close_reconnects_the_auto_reply_worker(self):
        main_source = _function_source(
            ROOT / "websocket/app/services/xianyu/xianyu_async.py",
            "XianyuAsync",
            "main",
        )
        normal_close_branch = main_source.split("闲鱼以正常关闭码断开", 1)[1].split(
            "finally:", 1
        )[0]

        self.assertIn("ConnectionState.RECONNECTING", normal_close_branch)
        self.assertIn('"WebSocket正常关闭"', normal_close_branch)
        self.assertIn("calculate_network_retry_delay()", normal_close_branch)
        self.assertIn("await self._interruptible_sleep(retry_delay)", normal_close_branch)
        self.assertIn("continue", normal_close_branch)


if __name__ == "__main__":
    unittest.main()
