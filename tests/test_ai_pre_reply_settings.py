from __future__ import annotations

import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from common.schemas.ai_reply import AIReplySettings, AIReplySettingsUpdate
from tests.auto_reply_test_harness import (
    load_ai_reply_engine_module,
    load_ai_reply_settings_service_module,
)


class AIReplySettingsDefaultsTest(unittest.TestCase):
    def test_pre_reply_defaults_are_disabled_and_safe_for_existing_accounts(self) -> None:
        settings = AIReplySettings()
        payload = settings.model_dump()

        self.assertEqual(payload.get("ai_pre_reply_enabled"), False)
        self.assertEqual(payload.get("ai_pre_reply_text"), "收到，稍等一下")
        self.assertEqual(payload.get("ai_pre_reply_cooldown_minutes"), 30)


class AIReplySettingsValidationTest(unittest.TestCase):
    def test_enabled_pre_reply_rejects_blank_text(self) -> None:
        with self.assertRaises(ValidationError):
            AIReplySettingsUpdate(
                ai_pre_reply_enabled=True,
                ai_pre_reply_text="  \n ",
            )

    def test_pre_reply_text_is_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            AIReplySettingsUpdate(ai_pre_reply_text="x" * 201)

    def test_pre_reply_cooldown_has_sensible_bounds(self) -> None:
        for value in (0, 1441):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                AIReplySettingsUpdate(ai_pre_reply_cooldown_minutes=value)

    def test_disabled_pre_reply_may_store_blank_text(self) -> None:
        settings = AIReplySettingsUpdate(
            ai_pre_reply_enabled=False,
            ai_pre_reply_text=" ",
        )

        self.assertEqual(settings.ai_pre_reply_text, " ")


class AIReplySettingsServiceTest(unittest.IsolatedAsyncioTestCase):
    class _Session:
        async def execute(self, _statement) -> None:
            return None

        async def commit(self) -> None:
            return None

    def test_service_returns_pre_reply_defaults_for_existing_accounts(self) -> None:
        module = load_ai_reply_settings_service_module()
        service = module.AIReplySettingsService(session=None)
        account = SimpleNamespace(metadata_json={})

        settings = service._extract_settings(account)

        self.assertEqual(settings.get("ai_pre_reply_enabled"), False)
        self.assertEqual(settings.get("ai_pre_reply_text"), "收到，稍等一下")
        self.assertEqual(settings.get("ai_pre_reply_cooldown_minutes"), 30)

    async def test_service_rejects_enabling_pre_reply_with_stored_blank_text(self) -> None:
        module = load_ai_reply_settings_service_module()
        service = module.AIReplySettingsService(session=self._Session())
        account = SimpleNamespace(
            id=1,
            metadata_json={
                "ai_reply_settings": {
                    "ai_pre_reply_enabled": False,
                    "ai_pre_reply_text": " ",
                }
            },
        )

        with self.assertRaisesRegex(ValueError, "确认文案不能为空"):
            await service.update_settings(
                account,
                {"ai_pre_reply_enabled": True},
            )


class AIReplyRuntimeSettingsTest(unittest.TestCase):
    def test_runtime_defaults_match_backend_defaults(self) -> None:
        module = load_ai_reply_engine_module()
        settings = module.AIReplyEngine()._get_default_settings()

        self.assertEqual(settings.get("ai_pre_reply_enabled"), False)
        self.assertEqual(settings.get("ai_pre_reply_text"), "收到，稍等一下")
        self.assertEqual(settings.get("ai_pre_reply_cooldown_minutes"), 30)


if __name__ == "__main__":
    unittest.main()
