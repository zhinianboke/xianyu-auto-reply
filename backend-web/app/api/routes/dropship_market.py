"""Firewall-only, read-only market collection contract for xianyu-dropship."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session as get_db
from app.core.config import get_settings
from common.models.xy_account import XYAccount
from common.schemas.common import ApiResponse

router = APIRouter(prefix="/integrations/dropship-market", tags=["Dropship integration"])


class DropshipMarketSearchRequest(BaseModel):
    account_ref: str = Field(..., min_length=1, max_length=128)
    keyword: str = Field(..., min_length=1, max_length=256)
    pages: int = Field(3, ge=1, le=10)
    page_size: int = Field(20, ge=1, le=50)
    detail_limit: int = Field(20, ge=0, le=50)


class DropshipMarketItemRequest(BaseModel):
    account_ref: str = Field(..., min_length=1, max_length=128)
    item_id: str = Field(..., min_length=6, max_length=32, pattern=r"^\d+$")


def _account_id_for_ref(account_ref: str) -> str | None:
    """Reverse only the opaque operator-configured pairing map."""
    raw = get_settings().dropship_account_refs_json
    try:
        mapping = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(mapping, dict):
        return None
    for account_id, configured_ref in mapping.items():
        if isinstance(configured_ref, str) and configured_ref == account_ref:
            return str(account_id)
    return None


@router.post("/search", response_model=ApiResponse)
async def search_market(
    request: DropshipMarketSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """Use the mapped adapter account to run a bounded, no-send search.

    Authentication is deferred only for the firewall-scoped HTTP pilot.  Do
    not publish this route through a public proxy before adding HMAC/HTTPS.
    """
    adapter_account_id = _account_id_for_ref(request.account_ref)
    if not adapter_account_id:
        raise HTTPException(404, "unbound account reference")
    result = await db.execute(select(XYAccount).where(XYAccount.account_id == adapter_account_id))
    account = result.scalar_one_or_none()
    if not account or account.status != "active" or not account.cookie:
        raise HTTPException(409, "mapped adapter account is unavailable")
    try:
        from app.services.compass.goofish_compass import GoofishCompassConfig, GoofishCompassService
        service = GoofishCompassService(
            user_id=str(account.id), cookie_value=account.cookie,
            config=GoofishCompassConfig(headless=True, detail_concurrency=3,
                navigation_timeout_ms=30000, network_idle_timeout_ms=15000,
                detail_response_timeout_ms=7000),
        )
        data = await service.search(
            keyword=request.keyword, start_page=1, pages=request.pages,
            page_size=request.page_size, fetch_detail=True, detail_limit=request.detail_limit,
        )
    except Exception:
        # Credentials and browser internals are intentionally omitted.
        return ApiResponse(success=False, message="market collector unavailable", data={"items": []})
    if data.get("error"):
        return ApiResponse(success=False, message=str(data["error"])[:300], data={"items": []})
    return ApiResponse(success=True, message="ok", data=data)


@router.post("/item", response_model=ApiResponse)
async def get_market_item(
    request: DropshipMarketItemRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """Re-collect one item detail using the account mapped to the hub.

    The endpoint is firewall-only during the HTTP pilot.  It is deliberately
    bounded to one numeric item ID and invokes no message or listing action.
    """
    adapter_account_id = _account_id_for_ref(request.account_ref)
    if not adapter_account_id:
        raise HTTPException(404, "unbound account reference")
    result = await db.execute(select(XYAccount).where(XYAccount.account_id == adapter_account_id))
    account = result.scalar_one_or_none()
    if not account or account.status != "active" or not account.cookie:
        raise HTTPException(409, "mapped adapter account is unavailable")
    try:
        from app.services.compass.goofish_compass import GoofishCompassConfig, GoofishCompassService
        service = GoofishCompassService(
            user_id=str(account.id), cookie_value=account.cookie,
            config=GoofishCompassConfig(headless=True, detail_concurrency=1,
                navigation_timeout_ms=30000, network_idle_timeout_ms=15000,
                detail_response_timeout_ms=7000),
        )
        data = await service.fetch_item_detail(item_id=request.item_id)
    except Exception:
        # Credentials and browser internals are intentionally omitted.
        return ApiResponse(success=False, message="market collector unavailable", data={"item": None})
    if data.get("error"):
        return ApiResponse(success=False, message=str(data["error"])[:300], data={"item": None})
    return ApiResponse(success=True, message="ok", data=data)
