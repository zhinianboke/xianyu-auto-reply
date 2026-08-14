"""
公开商品分类推荐接口。

功能：
1. 无需登录，通过分销秘钥校验调用用户。
2. 使用调用方指定的已启用闲鱼账号请求平台分类推荐。
3. 返回与单品发布界面一致的分类候选、动态属性和原始属性卡。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.routes.external_api_route import ExternalApiRoute
from app.services.external_account_service import (
    ExternalAccountAccessError,
    ExternalAccountService,
)
from app.services.platform_category_service import (
    CategoryRecommendationError,
    PlatformCategoryService,
)
from app.services.platform_category_selection import (
    CategorySelectionError,
    build_category_selection,
)
from common.schemas.common import ApiResponse


router = APIRouter(
    prefix="/external/category",
    tags=["公开分类推荐"],
    route_class=ExternalApiRoute,
)


class ExternalCategoryResponse(ApiResponse):
    """公开分类推荐统一响应。"""

    code: int


class ExternalCategoryRequest(BaseModel):
    """公开分类推荐请求参数。"""

    secret_key: str | None = None
    account_id: str | None = None
    description: str | None = None


class ExternalCategoryPropertiesRequest(ExternalCategoryRequest):
    """公开获取所选分类动态属性的请求参数。"""

    category: dict[str, Any] | None = None
    card_list: list[dict[str, Any]] | None = None


def _validate_common_fields(
    payload: ExternalCategoryRequest | None,
) -> tuple[str, str, str, ExternalCategoryResponse | None]:
    """校验两个公开分类接口共用的秘钥、账号 ID 和商品描述。"""
    secret_key = ((payload.secret_key if payload else "") or "").strip()
    account_id = ((payload.account_id if payload else "") or "").strip()
    description = ((payload.description if payload else "") or "").strip()

    validations = (
        (not secret_key, 40001, "秘钥不能为空"),
        (len(secret_key) > 128, 40001, "秘钥长度不能超过128位"),
        (not account_id, 40002, "闲鱼账号ID不能为空"),
        (len(account_id) > 80, 40002, "闲鱼账号ID长度不能超过80位"),
        (not description, 40004, "商品描述不能为空"),
        (len(description) > 1500, 40004, "商品描述长度不能超过1500位"),
    )
    for invalid, code, message in validations:
        if invalid:
            return secret_key, account_id, description, ExternalCategoryResponse(
                success=False,
                code=code,
                message=message,
                data=None,
            )
    return secret_key, account_id, description, None


async def _get_external_account(
    session: AsyncSession,
    secret_key: str,
    account_id: str,
) -> tuple[Any | None, ExternalCategoryResponse | None]:
    """校验秘钥和指定账号，统一转换账号查询异常。"""
    try:
        account = await ExternalAccountService(session).get_enabled_account_by_secret(
            secret_key,
            account_id,
        )
        return account, None
    except ExternalAccountAccessError as exc:
        return None, ExternalCategoryResponse(
            success=False,
            code=exc.code,
            message=exc.message,
            data=None,
        )
    except Exception as exc:
        logger.error(f"公开分类接口账号校验异常: account_id={account_id}, error={exc}")
        return None, ExternalCategoryResponse(
            success=False,
            code=50001,
            message="账号信息查询失败，请稍后重试",
            data=None,
        )


async def _request_platform_category(
    account: Any,
    description: str,
    selection: dict[str, Any] | None = None,
) -> ExternalCategoryResponse:
    """调用平台分类服务并统一返回公开接口响应。"""
    request_params = selection or {}
    try:
        data: dict[str, Any] = await PlatformCategoryService().recommend(
            title=description[:200],
            description=description,
            cookie=account.cookie,
            account_id=account.account_id,
            owner_id=account.owner_id,
            **request_params,
        )
    except CategoryRecommendationError as exc:
        logger.warning(
            f"公开分类接口请求失败: owner_id={account.owner_id}, "
            f"account_id={account.account_id}, error={exc}"
        )
        return ExternalCategoryResponse(
            success=False,
            code=40005,
            message=str(exc),
            data=None,
        )
    except Exception as exc:
        logger.error(
            f"公开分类接口异常: owner_id={account.owner_id}, "
            f"account_id={account.account_id}, error={exc}"
        )
        return ExternalCategoryResponse(
            success=False,
            code=40005,
            message="分类推荐失败，请稍后重试",
            data=None,
        )

    return ExternalCategoryResponse(
        success=True,
        code=200,
        message="分类推荐成功",
        data=data,
    )


@router.post("/recommend", response_model=ExternalCategoryResponse)
async def recommend_external_category(
    payload: ExternalCategoryRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalCategoryResponse:
    """
    根据商品描述获取指定闲鱼账号对应的平台分类信息。

    Args:
        payload: 分销秘钥、闲鱼账号 ID 和商品描述。
        session: 数据库会话。
    Returns:
        统一响应；成功数据结构与单品发布分类推荐接口一致。
    """
    secret_key, account_id, description, error = _validate_common_fields(payload)
    if error:
        return error
    account, error = await _get_external_account(session, secret_key, account_id)
    if error:
        return error
    return await _request_platform_category(account, description)


@router.post("/properties", response_model=ExternalCategoryResponse)
async def get_external_category_properties(
    payload: ExternalCategoryPropertiesRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalCategoryResponse:
    """
    根据分类推荐结果中选中的分类获取对应动态属性。

    Args:
        payload: 公共身份字段、商品描述、候选分类和完整属性卡。
        session: 数据库会话。
    Returns:
        统一响应；成功数据包含所选分类对应的 properties 和新 card_list。
    """
    secret_key, account_id, description, error = _validate_common_fields(payload)
    if error:
        return error
    if not payload or not isinstance(payload.category, dict):
        return ExternalCategoryResponse(
            success=False,
            code=40006,
            message="category不能为空，请传入分类推荐接口返回的完整候选分类",
            data=None,
        )
    if not isinstance(payload.card_list, list):
        return ExternalCategoryResponse(
            success=False,
            code=40006,
            message="card_list不能为空，请传入分类推荐接口返回的完整card_list",
            data=None,
        )
    if len(payload.card_list) > 100:
        return ExternalCategoryResponse(
            success=False,
            code=40006,
            message="card_list数量不能超过100条",
            data=None,
        )

    account, error = await _get_external_account(session, secret_key, account_id)
    if error:
        return error

    try:
        selection = build_category_selection(payload.card_list, payload.category)
    except CategorySelectionError as exc:
        return ExternalCategoryResponse(
            success=False,
            code=40006,
            message=str(exc),
            data=None,
        )

    response = await _request_platform_category(account, description, selection)
    if response.success:
        response.message = "分类属性获取成功"
    return response


__all__ = ["router"]
