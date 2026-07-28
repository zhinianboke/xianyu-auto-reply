from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from jose import JWTError
from pydantic import ValidationError

from app.api import deps
from app.api.routes.product_publish import (
    BatchPublishRequest,
    ExternalMaterialUpsertRequest,
)
from app.services.product_publish_service import (
    ProductMaterialService,
    _comparable_material_titles,
)
from common.models.user import UserStatus
from common.utils.security import generate_api_key, hash_api_key, mask_api_key
from common.utils.time_utils import get_beijing_now_naive


def external_item(index: int) -> dict:
    return {
        "external_id": str(index),
        "content_hash": f"{index:064x}",
        "title": f"【秒发】测试商品 {index}",
        "description": "测试简介",
        "price": 1,
        "images": [f"https://images.example/{index}.jpg"],
    }


class FakeResult:
    def __init__(self, user):
        self.user = user

    def scalar_one_or_none(self):
        return self.user

    def scalars(self):
        return self

    def first(self):
        return self.user


class FakeSession:
    def __init__(self, user):
        self.user = user
        self.commits = 0

    async def execute(self, _statement):
        return FakeResult(self.user)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _user):
        return None


class SequenceSession:
    def __init__(self, results):
        self.results = list(results)
        self.commits = 0

    async def execute(self, _statement):
        return FakeResult(self.results.pop(0))

    async def commit(self):
        self.commits += 1


class ApiKeySecurityTests(unittest.TestCase):
    def test_api_key_only_exposes_hash_and_mask(self):
        api_key = generate_api_key()
        digest = hash_api_key(api_key)

        self.assertTrue(api_key.startswith("xyk_"))
        self.assertEqual(len(digest), 64)
        self.assertNotIn(api_key, digest)
        self.assertTrue(mask_api_key(api_key).startswith(api_key[:8]))
        self.assertTrue(mask_api_key(api_key).endswith(api_key[-4:]))


class ExternalRequestValidationTests(unittest.TestCase):
    def test_external_material_limit_and_image_validation(self):
        request = ExternalMaterialUpsertRequest(
            source="gamer520",
            items=[external_item(index) for index in range(20)],
        )
        self.assertEqual(len(request.items), 20)

        with self.assertRaises(ValidationError):
            ExternalMaterialUpsertRequest(
                source="gamer520",
                items=[external_item(index) for index in range(21)],
            )

        invalid = external_item(1)
        invalid["images"] = ["file:///etc/passwd"]
        with self.assertRaises(ValidationError):
            ExternalMaterialUpsertRequest(
                source="gamer520",
                items=[invalid],
            )

    def test_batch_request_accepts_uuid_and_keeps_legacy_compatibility(self):
        request_id = "00000000-0000-4000-8000-000000000001"
        request = BatchPublishRequest(
            account_ids=["account-a"],
            material_ids=[1],
            request_id=request_id,
        )
        self.assertEqual(request.request_id, UUID(request_id))

        legacy = BatchPublishRequest(
            account_ids=["account-a"],
            material_ids=[1],
        )
        self.assertIsNone(legacy.request_id)

    def test_second_delivery_prefix_does_not_change_product_name(self):
        self.assertEqual(
            _comparable_material_titles("【秒发】  测试游戏 "),
            ["【秒发】 测试游戏", "测试游戏"],
        )


class ExternalMaterialDeduplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_same_name_material_is_skipped(self):
        duplicate = SimpleNamespace(
            id=88,
            source_content_hash="existing-hash",
        )
        session = SequenceSession([None, duplicate])
        service = ProductMaterialService(session)

        results = await service.upsert_external(
            user_id=1,
            source_type="gamer520",
            items=[external_item(1)],
        )

        self.assertEqual(results[0]["action"], "skipped")
        self.assertEqual(results[0]["material_id"], 88)
        self.assertIn("同名", results[0]["reason"])
        self.assertEqual(session.commits, 1)


class RestAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_jwt_and_api_key_resolve_the_same_user(self):
        user = SimpleNamespace(
            id=1,
            status=UserStatus.ACTIVE,
            api_key_last_used_at=get_beijing_now_naive(),
        )
        session = FakeSession(user)

        with patch.object(deps, "decode_token", return_value={"sub": "1"}):
            jwt_user = await deps.get_current_user(
                token="jwt-token",
                api_key=None,
                session=session,
            )
        api_user = await deps.get_current_user(
            token=None,
            api_key="xyk_test",
            session=session,
        )

        self.assertIs(jwt_user, user)
        self.assertIs(api_user, user)

    async def test_invalid_jwt_does_not_fall_back_to_api_key(self):
        user = SimpleNamespace(
            id=1,
            status=UserStatus.ACTIVE,
            api_key_last_used_at=get_beijing_now_naive(),
        )
        session = FakeSession(user)

        with patch.object(
            deps,
            "decode_token",
            side_effect=JWTError("invalid"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await deps.get_current_user(
                    token="invalid-jwt",
                    api_key="xyk_valid",
                    session=session,
                )
        self.assertEqual(raised.exception.status_code, 401)

    async def test_inactive_user_is_rejected_for_both_auth_methods(self):
        user = SimpleNamespace(status=UserStatus.INACTIVE)
        with self.assertRaises(HTTPException) as raised:
            await deps.get_current_active_user(user)
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
