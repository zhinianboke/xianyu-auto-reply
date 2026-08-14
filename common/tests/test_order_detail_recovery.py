import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


def _method_source(path: Path, class_name: str, method_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                    return ast.get_source_segment(source, child) or ""
    raise AssertionError(f"未找到 {class_name}.{method_name}")


class OrderDetailRecoveryTest(unittest.TestCase):
    def test_rate_limited_order_detail_uses_backoff_retry(self):
        source = _method_source(
            ROOT / "common/services/order_service.py",
            "OrderDetailService",
            "_fetch_order_detail",
        )

        self.assertIn("rate_limited = self._is_rate_limited_error(ret_list)", source)
        self.assertIn("retry_delay = 0.5 if token_expired else 5 * (retry_count + 1)", source)
        self.assertIn("await asyncio.sleep(retry_delay)", source)

    def test_rate_limit_detector_covers_platform_busy_response(self):
        source = _method_source(
            ROOT / "common/services/order_service.py",
            "OrderDetailService",
            "_is_rate_limited_error",
        )

        self.assertIn("fail_biz_common_system_error2", source)
        self.assertIn("闲鱼太累了", source)

    def test_redelivery_uses_order_detail_parser(self):
        source = _method_source(
            ROOT / "scheduler/app/services/scheduler/redelivery_task.py",
            "RedeliveryTask",
            "_process_order",
        )

        self.assertIn("OrderDetailService", source)
        self.assertIn("detail_service._parse_order_detail_response", source)
        self.assertNotIn("checker._parse_order_detail_response", source)
