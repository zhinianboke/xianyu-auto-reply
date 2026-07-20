"""Bridge chat-new push messages into the automation websocket service."""
from __future__ import annotations

from loguru import logger

from app.core.config import get_settings
from app.core.http_client import get_http_client


async def forward_message_to_automation(account_id: str, message_data: dict) -> None:
    """Forward one decrypted IM push message to the automation service."""
    if not account_id or not isinstance(message_data, dict):
        return

    try:
        settings = get_settings()
        url = (
            f"{settings.websocket_service_url.rstrip('/')}"
            f"/internal/accounts/{account_id}/ingest-message"
        )
        await get_http_client().post(
            url,
            json={"message_data": message_data, "source": "chat_new"},
        )
    except Exception as exc:
        logger.warning(f"【{account_id}】转发在线聊天推送到自动化服务失败: {exc}")
