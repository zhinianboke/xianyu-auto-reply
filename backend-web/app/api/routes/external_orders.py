"""公开订单查询接口。"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query
from loguru import logger
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.routes.external_api_route import ExternalApiRoute
from app.api.routes.external_shared import (
    ExternalApiResponse,
    external_error,
    normalize_text,
    validate_secret_key,
)
from app.services.external_order_service import (
    ExternalOrderAccessError,
    ExternalOrderQueryService,
)


router = APIRouter(
    prefix="/external/orders",
    tags=["公开订单查询"],
    route_class=ExternalApiRoute,
)


class ExternalOrderListRequest(BaseModel):
    """公开订单查询请求。"""

    secret_key: str | None = Field(default=None, max_length=128)
    item_ids: list[str] = Field(default_factory=list, max_length=100)
    item_id: str | None = Field(default=None, max_length=1000)
    order_no: str | None = Field(default=None, max_length=64)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


def _normalize_item_ids(
    payload: ExternalOrderListRequest,
) -> tuple[list[str] | None, str | None]:
    """合并数组和逗号分隔的商品 ID，并校验显式传入的空值。"""
    raw_values = list(payload.item_ids)
    if payload.item_id is not None:
        raw_values.extend(payload.item_id.split(","))
    if not raw_values:
        return None, None

    item_ids: list[str] = []
    for value in raw_values:
        for part in value.split(","):
            normalized = normalize_text(part)
            if len(normalized) > 64:
                return None, "商品ID长度不能超过64位"
            if normalized and normalized not in item_ids:
                item_ids.append(normalized)
    if not item_ids:
        return None, "商品ID不能为空"
    if len(item_ids) > 100:
        return None, "商品ID数量不能超过100个"
    return item_ids, None


async def _query_external_orders(
    payload: ExternalOrderListRequest,
    session: AsyncSession,
) -> ExternalApiResponse:
    """按秘钥查询订单，可按多个商品 ID 或订单号筛选并分页。"""
    secret_key, error = validate_secret_key(payload.secret_key)
    if error:
        return error
    item_ids, item_error = _normalize_item_ids(payload)
    if item_error:
        return external_error(40008, item_error)
    order_no = normalize_text(payload.order_no)

    try:
        data = await ExternalOrderQueryService(session).list_orders(
            secret_key,
            item_ids=item_ids,
            order_no=order_no or None,
            page=payload.page,
            page_size=payload.page_size,
        )
    except ExternalOrderAccessError as exc:
        return external_error(exc.code, exc.message)
    except Exception as exc:
        logger.error(
            f"公开订单查询异常: page={payload.page}, page_size={payload.page_size}, "
            f"item_ids={item_ids}, order_no={order_no}, error={exc}"
        )
        return external_error(50001, "订单信息查询失败，请稍后重试")

    return ExternalApiResponse(
        success=True,
        code=200,
        message="订单查询成功",
        data=data,
    )


@router.post("", response_model=ExternalApiResponse)
async def list_external_orders(
    payload: ExternalOrderListRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalApiResponse:
    """使用 JSON 请求体查询公开订单。"""
    if payload is None:
        return external_error(40008, "请求参数不能为空")
    return await _query_external_orders(payload, session)


@router.get("", response_model=ExternalApiResponse)
async def get_external_orders(
    secret_key: str | None = Query(default=None, description="分销秘钥"),
    item_id: list[str] | None = Query(default=None, description="商品ID，可重复传入多个"),
    item_ids: list[str] | None = Query(default=None, description="商品ID，可重复传入或使用逗号分隔"),
    order_no: str | None = Query(default=None, description="订单号，精确查询"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalApiResponse:
    """使用查询参数查询公开订单，商品 ID 支持重复参数或逗号分隔。"""
    query_item_ids: list[str] = []
    for value in (item_id or []) + (item_ids or []):
        query_item_ids.extend(value.split(","))
    if len(query_item_ids) > 100:
        return external_error(40008, "商品ID数量不能超过100个")
    try:
        payload = ExternalOrderListRequest(
            secret_key=secret_key,
            item_ids=query_item_ids,
            order_no=order_no,
            page=page,
            page_size=page_size,
        )
    except ValidationError:
        return external_error(40008, "请求参数格式不正确")
    return await _query_external_orders(payload, session)


__all__ = ["router"]
