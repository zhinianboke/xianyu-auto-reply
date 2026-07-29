"""Best-effort, no-send HTTP bridge for the initial xianyu-dropship pilot."""
from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from loguru import logger

from app.core.config import get_settings


class DropshipBridge:
    """Mirror buyer messages and account stops without exposing a send action."""

    @staticmethod
    def _account_refs(raw_mapping: str) -> dict[str, str]:
        try:
            parsed = json.loads(raw_mapping or "{}")
        except (TypeError, ValueError):
            logger.warning("xianyu-dropship bridge account mapping is invalid")
            return {}
        if not isinstance(parsed, dict):
            logger.warning("xianyu-dropship bridge account mapping must be an object")
            return {}
        return {
            str(adapter_account_id): account_ref.strip()
            for adapter_account_id, account_ref in parsed.items()
            if isinstance(account_ref, str) and account_ref.strip()
        }

    def _account_ref(self, adapter_account_id: str) -> str | None:
        settings = get_settings()
        return self._account_refs(settings.dropship_account_refs_json).get(str(adapter_account_id))

    async def _post(self, payload: dict[str, Any]) -> bool:
        settings = get_settings()
        endpoint = settings.dropship_webhook_url.strip()
        if not endpoint:
            return False
        try:
            async with httpx.AsyncClient(timeout=settings.dropship_bridge_timeout_seconds) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            # Never log chat contents, image links, cookies, or the endpoint.
            logger.warning("xianyu-dropship bridge delivery failed: {}", type(exc).__name__)
            return False

    async def publish_message(
        self,
        adapter_account_id: str,
        own_user_id: str,
        parsed_message: dict[str, Any],
    ) -> bool:
        account_ref = self._account_ref(adapter_account_id)
        message_id = parsed_message.get("message_id")
        sender_id = parsed_message.get("send_user_id")
        conversation_id = parsed_message.get("chat_id")
        if not account_ref or not isinstance(message_id, str) or not message_id:
            return False
        if sender_id == own_user_id or not isinstance(conversation_id, str) or not conversation_id:
            return False

        image_urls = parsed_message.get("image_urls")
        if not isinstance(image_urls, list):
            image_urls = []
        payload = {
            "kind": "message",
            "account_ref": account_ref,
            "message_id": message_id[:128],
            "conversation_id": conversation_id[:128],
            "buyer_id": str(sender_id or "")[:128] or None,
            "buyer_nickname": str(parsed_message.get("send_user_name") or "")[:256] or None,
            "message_type": str(parsed_message.get("message_type") or "text")[:32],
            "content": str(parsed_message.get("send_message") or "")[:20_000] or None,
            "image_urls": [str(url)[:2048] for url in image_urls[:20]],
            "item_id": str(parsed_message.get("item_id") or "")[:128] or None,
            # Item detail snapshots are intentionally collected by the central
            # system later; never pass the adapter's raw platform packet here.
            "item_snapshot": None,
        }
        return await self._post(payload)

    async def publish_account_stop(self, adapter_account_id: str, status: str) -> bool:
        account_ref = self._account_ref(adapter_account_id)
        if not account_ref:
            return False
        return await self._post({
            "kind": "account_status",
            "account_ref": account_ref,
            "event_id": str(uuid.uuid4()),
            "status": status,
        })


dropship_bridge = DropshipBridge()
