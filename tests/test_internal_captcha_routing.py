from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
WEBSOCKET_ROOT = REPO_ROOT / "websocket"
if str(WEBSOCKET_ROOT) not in sys.path:
    sys.path.insert(0, str(WEBSOCKET_ROOT))

from app.api.routes import internal  # noqa: E402
from common.db.compat import db_manager  # noqa: E402
from common.services.captcha.routing_settings import (  # noqa: E402
    CaptchaRoutingSettings,
)


class InternalCaptchaRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_internal_request_relays_to_configured_remote_worker(self):
        remote_config = {
            "url": "http://worker/slider-solve",
            "secret": "secret",
            "pass_cookies": True,
            "device_id": "device-1",
            "allow_local_fallback": False,
        }
        browser_runner = AsyncMock(return_value=(True, {"x5sec": "ok"}, "remote"))
        real_mouse_runner = AsyncMock()

        with (
            patch.object(
                internal,
                "load_captcha_routing_settings",
                new=AsyncMock(
                    return_value=CaptchaRoutingSettings(
                        remote_config=remote_config,
                        local_slider_disabled=False,
                    )
                ),
            ),
            patch.object(
                internal,
                "refresh_slider_mode_from_database",
                new=AsyncMock(return_value="real_mouse"),
            ),
            patch.object(internal, "run_browser_task", new=browser_runner),
            patch.object(
                internal.real_mouse_weighted_runner,
                "submit",
                new=real_mouse_runner,
            ),
            patch.object(db_manager, "update_risk_control_log", return_value=True),
        ):
            result = await internal.solve_captcha(
                internal.SolveCaptchaRequest(
                    account_id="account-1",
                    url="https://example.invalid/punish",
                    call_type="local",
                    cookies="unb=1",
                    device_id="device-1",
                    risk_log_id=123,
                )
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["engine"], "remote")
        self.assertIs(browser_runner.await_args.args[8], remote_config)
        real_mouse_runner.assert_not_awaited()

    async def test_local_disabled_without_remote_never_starts_browser(self):
        browser_runner = AsyncMock()
        real_mouse_runner = AsyncMock()

        with (
            patch.object(
                internal,
                "load_captcha_routing_settings",
                new=AsyncMock(
                    return_value=CaptchaRoutingSettings(
                        remote_config=None,
                        local_slider_disabled=True,
                    )
                ),
            ),
            patch.object(internal, "run_browser_task", new=browser_runner),
            patch.object(
                internal.real_mouse_weighted_runner,
                "submit",
                new=real_mouse_runner,
            ),
            patch.object(db_manager, "update_risk_control_log", return_value=True),
        ):
            result = await internal.solve_captcha(
                internal.SolveCaptchaRequest(
                    account_id="account-1",
                    url="https://example.invalid/punish",
                    call_type="local",
                    risk_log_id=123,
                )
            )

        self.assertFalse(result["success"])
        self.assertIn("本机滑块不处理已开启", result["message"])
        browser_runner.assert_not_awaited()
        real_mouse_runner.assert_not_awaited()

    async def test_external_request_is_executed_here_instead_of_relayed(self):
        routing_loader = AsyncMock()
        browser_runner = AsyncMock()
        real_mouse_runner = AsyncMock(
            return_value=(True, {"x5sec": "ok"}, "real_mouse")
        )

        with (
            patch.object(
                internal,
                "load_captcha_routing_settings",
                new=routing_loader,
            ),
            patch.object(
                internal,
                "refresh_slider_mode_from_database",
                new=AsyncMock(return_value="real_mouse"),
            ),
            patch.object(internal, "run_browser_task", new=browser_runner),
            patch.object(
                internal.real_mouse_weighted_runner,
                "submit",
                new=real_mouse_runner,
            ),
            patch.object(db_manager, "update_risk_control_log", return_value=True),
        ):
            result = await internal.solve_captcha(
                internal.SolveCaptchaRequest(
                    account_id="external-account",
                    url="https://example.invalid/punish",
                    call_type="remote",
                    risk_log_id=123,
                )
            )

        self.assertTrue(result["success"])
        routing_loader.assert_not_awaited()
        real_mouse_runner.assert_awaited_once()
        browser_runner.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
