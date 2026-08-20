from __future__ import annotations

import unittest
from unittest.mock import patch

from common.services.captcha.orchestrator import (
    run_slider_verification_with_fallback,
)
from common.services.captcha.routing_settings import (
    build_captcha_routing_settings,
)


class CaptchaRoutingSettingsTests(unittest.TestCase):
    def test_remote_route_carries_device_only_when_cookie_forwarding_enabled(self):
        routing = build_captcha_routing_settings(
            {
                "captcha.remote_service_url": "http://worker/slider-solve",
                "captcha.remote_secret_key": "secret",
                "captcha.remote_pass_cookies": "true",
                "captcha.local_slider_disabled": "true",
            },
            device_id="device-1",
        )

        self.assertTrue(routing.local_slider_disabled)
        self.assertIsNotNone(routing.remote_config)
        self.assertEqual(routing.remote_config["device_id"], "device-1")
        self.assertTrue(routing.remote_config["pass_cookies"])
        self.assertFalse(routing.remote_config["allow_local_fallback"])

    def test_incomplete_remote_route_does_not_enable_remote_service(self):
        routing = build_captcha_routing_settings(
            {
                "captcha.remote_service_url": "http://worker/slider-solve",
                "captcha.remote_secret_key": "",
                "captcha.local_slider_disabled": "true",
            }
        )

        self.assertIsNone(routing.remote_config)
        self.assertTrue(routing.local_slider_disabled)

    def test_configured_remote_route_is_remote_only(self):
        routing = build_captcha_routing_settings(
            {
                "captcha.remote_service_url": "http://worker/slider-solve",
                "captcha.remote_secret_key": "secret",
                "captcha.local_slider_disabled": "false",
            }
        )

        self.assertIsNotNone(routing.remote_config)
        self.assertFalse(routing.remote_config["allow_local_fallback"])


class RemoteFallbackPolicyTests(unittest.TestCase):
    def test_remote_only_route_never_starts_local_slider_after_network_failure(self):
        with (
            patch(
                "common.services.captcha.orchestrator._call_remote_solve",
                return_value=("fallback", None, "worker unavailable"),
            ),
            patch(
                "common.services.captcha.orchestrator.run_slider_verification"
            ) as local_solver,
        ):
            result = run_slider_verification_with_fallback(
                "account-1",
                "https://example.invalid/punish",
                remote_config={
                    "url": "http://worker/slider-solve",
                    "secret": "secret",
                    "pass_cookies": True,
                    "device_id": "device-1",
                    "allow_local_fallback": False,
                },
                existing_cookies_str="unb=1",
                slider_mode="playwright",
            )

        self.assertEqual(
            result,
            (False, None, "remote:worker unavailable"),
        )
        local_solver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
