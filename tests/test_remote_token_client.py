from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from common.services.captcha.token_response import summarize_token_response_for_log
from common.services.captcha.token_refetch import request_fresh_captcha_url
from common.services.im_token_api import (
    ImTokenApiResult,
    _attach_remote_failure,
    _request_remote_token_from_settings,
    _remote_result_to_im_token_result,
    request_im_token_with_fallback,
)
from common.services.remote_token_api import RemoteTokenResult, _parse_remote_token_response
from common.services.remote_token_risk_log_service import (
    REMOTE_OUTCOME_CAPTCHA_REQUIRED,
    REMOTE_TOKEN_STATUS_CAPTCHA_REQUIRED,
    build_remote_fallback_event_description,
    build_remote_token_log_result,
    record_remote_token_risk_log_sync,
)
from common.services.token_api_mode import TOKEN_API_MODE_REMOTE


class RemoteTokenClientCompatibilityTests(unittest.TestCase):
    def test_captcha_challenge_is_not_described_as_token_failure(self):
        description = build_remote_fallback_event_description(
            local_failure_reason="未返回有效Token",
            remote_outcome=REMOTE_OUTCOME_CAPTCHA_REQUIRED,
        )
        result = build_remote_token_log_result(
            success=False,
            captcha_required=True,
            message="远程节点触发滑块验证",
            api_mode="web",
            status_code=200,
        )

        self.assertIn("远程接口需要滑块验证", description)
        self.assertNotIn("远程接口获取Token失败", description)
        self.assertTrue(result.startswith("远程接口需要滑块验证"))

    def test_sync_risk_log_uses_captcha_required_status_without_error(self):
        with (
            patch(
                "common.services.remote_token_risk_log_service.db_manager.add_risk_control_log",
                return_value=123,
            ) as add_log,
            patch(
                "common.services.remote_token_risk_log_service.db_manager.update_risk_control_log",
                return_value=True,
            ) as update_log,
        ):
            record_remote_token_risk_log_sync(
                account_identifier="account-1",
                success=False,
                captcha_required=True,
                message="远程节点触发滑块验证",
            )

        self.assertEqual(
            add_log.call_args.kwargs["processing_status"],
            REMOTE_TOKEN_STATUS_CAPTCHA_REQUIRED,
        )
        self.assertIsNone(update_log.call_args.kwargs["error_message"])

    def test_token_log_summary_redacts_credentials(self):
        summary = summarize_token_response_for_log(
            {
                "ret": ["FAIL_SYS_USER_VALIDATE"],
                "data": {
                    "url": "https://h5api.m.goofish.com/punish?x5secdata=secret",
                    "accessToken": "do-not-log",
                },
            }
        )
        self.assertNotIn("x5secdata", summary)
        self.assertNotIn("do-not-log", summary)
        self.assertIn("https://h5api.m.goofish.com/punish", summary)

    def test_worker_cookie_updates_are_propagated_to_main_flow(self):
        result = _parse_remote_token_response(
            {
                "success": True,
                "message": "ok",
                "data": {
                    "token": "access-token",
                    "device_id": "device-id",
                    "api_mode": "web",
                    "cookies": {
                        "_m_h5_tk": "fresh-token",
                        "x5sec": "verified",
                    },
                },
            },
            status_code=200,
            duration_seconds=0.1,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.cookies["x5sec"], "verified")
        converted = _remote_result_to_im_token_result(result, "old-device")
        self.assertEqual(converted.response_cookies["_m_h5_tk"], "fresh-token")

    def test_worker_captcha_url_replaces_business_server_url(self):
        result = _parse_remote_token_response(
            {
                "success": False,
                "message": "远程节点触发滑块验证",
                "data": {
                    "device_id": "remote-device",
                    "api_mode": "web",
                    "captcha_url": (
                        "https://h5api.m.goofish.com/a/punish?x5secdata=remote"
                    ),
                    "cookies": {"_m_h5_tk": "remote-fresh"},
                },
            },
            status_code=200,
            duration_seconds=0.1,
        )

        self.assertFalse(result.success)
        self.assertIn("x5secdata=remote", result.captcha_url)
        converted = _remote_result_to_im_token_result(result, "local-device")
        self.assertEqual(converted.device_id, "remote-device")
        self.assertEqual(
            converted.response_json["data"]["url"],
            result.captcha_url,
        )
        self.assertEqual(converted.response_cookies["_m_h5_tk"], "remote-fresh")
        local = ImTokenApiResult(
            response_json={
                "ret": ["FAIL_SYS_USER_VALIDATE::local"],
                "data": {
                    "url": "https://h5api.m.goofish.com/a/punish?x5secdata=local"
                },
            },
            response_cookies={"local-cookie": "kept"},
            status_code=200,
            duration_seconds=0.1,
            device_id="local-device",
        )
        selected = _attach_remote_failure(local, converted)
        self.assertIn("x5secdata=remote", selected.response_json["data"]["url"])
        self.assertEqual(selected.response_cookies["local-cookie"], "kept")
        self.assertEqual(
            selected.response_cookies["_m_h5_tk"],
            "remote-fresh",
        )

    def test_refetched_remote_url_is_not_overwritten_by_local_url(self):
        local_url = "https://h5api.m.goofish.com/a/punish?x5secdata=local"
        remote_url = "https://h5api.m.goofish.com/a/punish?x5secdata=remote"

        def remote_fallback(_cookie_id, result, **_kwargs):
            result["fresh_url"] = remote_url
            result["device_id"] = "remote-device"
            return False

        with (
            patch(
                "common.services.captcha.token_refetch.load_token_api_mode_sync",
                return_value=TOKEN_API_MODE_REMOTE,
            ),
            patch(
                "common.services.captcha.token_refetch._request_token_api_with_expiry_retry",
                return_value=(
                    {
                        "ret": ["FAIL_SYS_USER_VALIDATE::local"],
                        "data": {"url": local_url},
                    },
                    {},
                    {"unb": "123", "_m_h5_tk": "old_123"},
                    "unb=123; _m_h5_tk=old_123",
                ),
            ),
            patch(
                "common.services.captcha.token_refetch._try_remote_token_fallback",
                side_effect=remote_fallback,
            ),
        ):
            result = request_fresh_captcha_url(
                "account-1",
                {"unb": "123", "_m_h5_tk": "old_123"},
                "unb=123; _m_h5_tk=old_123",
                "local-device",
            )

        self.assertEqual(result["fresh_url"], remote_url)
        self.assertEqual(result["device_id"], "remote-device")


class RemoteTokenAsyncFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_remote_captcha_response_is_logged_as_required_not_failed(self):
        remote_result = RemoteTokenResult(
            success=False,
            message="远程节点触发滑块验证",
            response_json={},
            status_code=200,
            duration_seconds=0.2,
            device_id="remote-device",
            api_mode="web",
            captcha_url="https://h5api.m.goofish.com/punish?x5secdata=secret",
        )
        with (
            patch(
                "common.services.im_token_api.request_remote_xianyu_token_from_settings",
                new=AsyncMock(return_value=remote_result),
            ),
            patch(
                "common.services.im_token_api.record_remote_token_risk_log",
                new=AsyncMock(),
            ) as record_log,
        ):
            result = await _request_remote_token_from_settings(
                "local-device",
                cookies="unb=123",
                timeout_seconds=5,
                log_tag="account-1",
                local_failure_reason="未返回有效Token",
            )

        self.assertIn("FAIL_SYS_USER_VALIDATE", result.response_json["ret"][0])
        self.assertTrue(record_log.call_args.kwargs["captcha_required"])
        self.assertIn(
            "远程接口需要滑块验证",
            record_log.call_args.kwargs["event_description"],
        )

    async def test_local_exception_keeps_remote_captcha_context(self):
        remote = ImTokenApiResult(
            response_json={
                "ret": ["FAIL_SYS_USER_VALIDATE::remote"],
                "data": {
                    "url": (
                        "https://h5api.m.goofish.com/a/punish?x5secdata=remote"
                    )
                },
            },
            response_cookies={"_m_h5_tk": "remote-fresh"},
            status_code=200,
            duration_seconds=0.1,
            api_mode=TOKEN_API_MODE_REMOTE,
            device_id="remote-device",
        )
        with (
            patch(
                "common.services.im_token_api.request_im_token",
                new=AsyncMock(side_effect=RuntimeError("local unavailable")),
            ),
            patch(
                "common.services.im_token_api._try_remote_token_fallback",
                new=AsyncMock(return_value=remote),
            ),
        ):
            selected = await request_im_token_with_fallback(
                "unb=123; _m_h5_tk=old_123",
                "local-device",
                api_mode=TOKEN_API_MODE_REMOTE,
            )

        self.assertIs(selected, remote)
        self.assertEqual(selected.device_id, "remote-device")
        self.assertIn("x5secdata=remote", selected.response_json["data"]["url"])


if __name__ == "__main__":
    unittest.main()
