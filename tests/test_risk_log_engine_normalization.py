from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEBSOCKET_ROOT = REPO_ROOT / "websocket"
if str(WEBSOCKET_ROOT) not in sys.path:
    sys.path.insert(0, str(WEBSOCKET_ROOT))

from app.utils.captcha_engine import normalize_captcha_engine  # noqa: E402


class CaptchaEngineNormalizationTests(unittest.TestCase):
    def test_remote_diagnostic_is_stored_as_engine_and_error(self):
        reason = "('Connection aborted.', RemoteDisconnected('Remote end closed'))"

        engine, error = normalize_captcha_engine(f"remote:{reason}")

        self.assertEqual(engine, "remote")
        self.assertEqual(error, reason)

    def test_existing_error_is_not_overwritten(self):
        engine, error = normalize_captcha_engine(
            "remote:transport detail",
            "上层返回的失败原因",
        )

        self.assertEqual(engine, "remote")
        self.assertEqual(error, "上层返回的失败原因")

    def test_unknown_long_engine_is_bounded(self):
        engine, error = normalize_captcha_engine("x" * 64)

        self.assertEqual(len(engine), 32)
        self.assertEqual(error, f"滑块引擎返回异常标识: {'x' * 64}")


if __name__ == "__main__":
    unittest.main()
