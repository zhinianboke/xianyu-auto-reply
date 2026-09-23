"""公开消息日志查询接口。"""
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
from app.services.external_message_log_service import (
    ExternalMessageLogAccessError,
    ExternalMessageLogQueryService,
)


router = APIRouter(
    prefix="/external/message-logs",
    tags=["公开消息日志"],
    route_class=ExternalApiRoute,
)


class ExternalMessageLogRequest(BaseModel):
    """公开消息日志查询请求。"""

    secret_key: str | None = Field(default=None, max_length=128)
    item_id: str | None = Field(default=None, max_length=64)
    message_type: str = Field(default="auto_reply", pattern="^(auto_reply|auto_delivery)$")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


async def _query_external_message_logs(
    payload: ExternalMessageLogRequest,
    session: AsyncSession,
) -> ExternalApiResponse:
    """校验公开请求并按商品 ID 查询消息日志。"""
    secret_key, error = validate_secret_key(payload.secret_key)
    if error:
        return error

    item_id = normalize_text(payload.item_id)
    if not item_id:
        return external_error(40008, "商品ID不能为空")
    if len(item_id) > 64:
        return external_error(40008, "商品ID长度不能超过64位")

    try:
        data = await ExternalMessageLogQueryService(session).list_logs(
            secret_key,
            item_id=item_id,
            message_type=payload.message_type,
            page=payload.page,
            page_size=payload.page_size,
        )
    except ExternalMessageLogAccessError as exc:
        return external_error(exc.code, exc.message)
    except Exception as exc:
        logger.error(
            f"公开消息日志查询异常: item_id={item_id}, message_type={payload.message_type}, "
            f"page={payload.page}, page_size={payload.page_size}, error={exc}"
        )
        return external_error(50001, "消息日志查询失败，请稍后重试")

    return ExternalApiResponse(
        success=True,
        code=200,
        message="消息日志查询成功",
        data=data,
    )


@router.post("", response_model=ExternalApiResponse)
async def list_external_message_logs(
    payload: ExternalMessageLogRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalApiResponse:
    """使用 JSON 请求体按商品 ID 查询公开消息日志。"""
    if payload is None:
        return external_error(40008, "请求参数不能为空")
    return await _query_external_message_logs(payload, session)


@router.get("", response_model=ExternalApiResponse)
async def get_external_message_logs(
    secret_key: str | None = Query(default=None, description="分销秘钥"),
    item_id: str | None = Query(default=None, description="商品ID"),
    message_type: str = Query(default="auto_reply", description="消息类型：auto_reply/auto_delivery"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalApiResponse:
    """使用查询参数按商品 ID 查询公开消息日志。"""
    try:
        payload = ExternalMessageLogRequest(
            secret_key=secret_key,
            item_id=item_id,
            message_type=message_type,
            page=page,
            page_size=page_size,
        )
    except ValidationError:
        return external_error(40008, "请求参数格式不正确")
    return await _query_external_message_logs(payload, session)


__all__ = ["router"]
