"""Firewall-only manual text-reply contract for the xianyu-dropship hub."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session as get_db
from app.core.config import get_settings
from app.services.websocket_client import WebSocketServiceClient
from common.models.xy_account import XYAccount
from common.schemas.common import ApiResponse

router = APIRouter(prefix="/integrations/dropship-chat", tags=["Dropship integration"])


class DropshipManualReplyRequest(BaseModel):
    account_ref: str = Field(..., min_length=1, max_length=128)
    conversation_id: str = Field(..., min_length=1, max_length=128)
    content: str = Field(..., min_length=1, max_length=1000)


def _account_id_for_ref(account_ref: str) -> str | None:
    """Reverse only the opaque operator-configured one-to-one pairing map."""
    try:
        mapping = json.loads(get_settings().dropship_account_refs_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(mapping, dict):
        return None
    for account_id, configured_ref in mapping.items():
        if isinstance(configured_ref, str) and configured_ref == account_ref:
            return str(account_id)
    return None


@router.post("/reply", response_model=ApiResponse)
async def send_manual_reply(
    request: DropshipManualReplyRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """Deliver text only after an operator clicked send in the central workbench.

    This endpoint is intentionally limited to the firewall-scoped HTTP pilot.
    It has no automatic-send path and never accepts image uploads.
    """
    adapter_account_id = _account_id_for_ref(request.account_ref)
    if not adapter_account_id:
        raise HTTPException(404, "unbound account reference")
    result = await db.execute(select(XYAccount).where(XYAccount.account_id == adapter_account_id))
    account = result.scalar_one_or_none()
    if not account or account.status != "active" or not account.cookie:
        raise HTTPException(409, "mapped adapter account is unavailable")
    delivery = await WebSocketServiceClient().send_message(
        adapter_account_id, request.conversation_id, request.content.strip(), "text",
    )
    if not isinstance(delivery, dict) or delivery.get("success") is False:
        return ApiResponse(success=False, message="manual reply could not be delivered")
    return ApiResponse(success=True, message="manual reply delivered", data={"conversation_id": request.conversation_id})
