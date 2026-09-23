"""
公开商品分类推荐接口。

功能：
1. 无需登录，通过分销秘钥校验调用用户。
2. 使用调用方指定的闲鱼账号请求平台分类推荐，不限制账号启用状态。
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
from app.api.routes.external_shared import (
    ExternalApiResponse,
    external_error,
    normalize_text,
    resolve_external_account,
    validate_identity_fields,
)
from app.services.platform_category_service import (
    CategoryRecommendationError,
    PlatformCategoryService,
)
from app.services.platform_category_selection import (
    CategorySelectionError,
    build_category_selection,
)


router = APIRouter(
    prefix="/external/category",
    tags=["公开分类推荐"],
    route_class=ExternalApiRoute,
)


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
) -> tuple[str, str, str, ExternalApiResponse | None]:
    """
    校验两个公开分类接口共用的秘钥、账号 ID 和商品描述。

    秘钥和账号 ID 走公开接口公共校验，商品描述为分类接口特有字段。

    Args:
        payload: 公开分类接口请求体。
    Returns:
        规范化后的秘钥、账号 ID、商品描述和错误响应。
    """
    secret_key, account_id, error = validate_identity_fields(
        payload.secret_key if payload else None,
        payload.account_id if payload else None,
    )
    description = normalize_text(payload.description if payload else None)
    if error:
        return secret_key, account_id, description, error
    if not description:
        return secret_key, account_id, description, external_error(40004, "商品描述不能为空")
    if len(description) > 1500:
        return secret_key, account_id, description, external_error(40004, "商品描述长度不能超过1500位")
    return secret_key, account_id, description, None


async def _request_platform_category(
    account: Any,
    description: str,
    selection: dict[str, Any] | None = None,
) -> ExternalApiResponse:
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
        return external_error(40005, str(exc))
    except Exception as exc:
        logger.error(
            f"公开分类接口异常: owner_id={account.owner_id}, "
            f"account_id={account.account_id}, error={exc}"
        )
        return external_error(40005, "分类推荐失败，请稍后重试")

    return ExternalApiResponse(
        success=True,
        code=200,
        message="分类推荐成功",
        data=data,
    )


@router.post("/recommend", response_model=ExternalApiResponse)
async def recommend_external_category(
    payload: ExternalCategoryRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalApiResponse:
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
    account, error = await resolve_external_account(session, secret_key, account_id, "公开分类接口")
    if error:
        return error
    return await _request_platform_category(account, description)


@router.post("/properties", response_model=ExternalApiResponse)
async def get_external_category_properties(
    payload: ExternalCategoryPropertiesRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalApiResponse:
    """
    根据分类推荐结果中选中的分类获取对应动态属性。

    与单品发布一致，category 只需能定位分类的任意一个标识
    （channel_cat_id、tb_cat_id、cat_name 任一，或分类卡自带 catId 时的 cat_id），
    其余分类信息从 card_list 中回填，无需调用方传齐。
    最稳妥的用法是把推荐接口 candidates 里选中的那个对象原样回传。

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
        return external_error(40006, "category不能为空，请传入分类推荐接口返回的完整候选分类")
    if not isinstance(payload.card_list, list):
        return external_error(40006, "card_list不能为空，请传入分类推荐接口返回的完整card_list")
    if len(payload.card_list) > 100:
        return external_error(40006, "card_list数量不能超过100条")

    account, error = await resolve_external_account(session, secret_key, account_id, "公开分类接口")
    if error:
        return error

    try:
        selection = build_category_selection(payload.card_list, payload.category)
    except CategorySelectionError as exc:
        return external_error(40006, str(exc))

    response = await _request_platform_category(account, description, selection)
    if response.success:
        response.message = "分类属性获取成功"
    return response


__all__ = ["router"]
