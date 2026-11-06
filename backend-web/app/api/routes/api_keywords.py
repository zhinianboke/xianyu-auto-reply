"""API关键词新建、编辑及配置查询接口，不触发自动回复、发货或外部API请求。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query
from loguru import logger
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.services.api_keyword_service import ApiKeywordService
from common.models.user import User
from common.schemas.api_keyword import ApiKeywordCreate, ApiKeywordUpdate
from common.schemas.common import ApiResponse
from common.utils.auth_scope import resolve_owner_scope

router = APIRouter(prefix="/api-keywords", tags=["API关键词"])
CurrentUser = Annotated[User, Depends(deps.get_current_active_user)]
DatabaseSession = Annotated[AsyncSession, Depends(deps.get_db_session)]
RuleId = Annotated[int, Path(ge=1, le=9223372036854775807)]


def _validation_message(exc: ValidationError) -> str:
    """把新建和修改的字段校验错误统一转换为中文提示。"""
    return str(exc.errors()[0].get("ctx", {}).get("error") or "表单字段缺失或类型不正确，请检查后保存")


@router.get("/options", response_model=ApiResponse)
async def get_api_keyword_options(
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ApiResponse:
    """登录用户读取API关键词方法和参数的中文字典。"""
    user_id = current_user.id
    try:
        return ApiResponse(success=True, message="查询成功", data=await ApiKeywordService(session).get_options())
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    except SQLAlchemyError:
        logger.exception("API关键词字典查询失败: user_id={}", user_id)
        return ApiResponse(success=False, code=50001, message="读取API关键词选项失败，请稍后重试")


@router.get("", response_model=ApiResponse)
async def list_api_keywords(
    current_user: CurrentUser,
    session: DatabaseSession,
    account_id: str = Query(default="", max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse:
    """按账号查询权限范围内的配置，使用后端分页。"""
    user_id = current_user.id
    owner_id, _ = resolve_owner_scope(current_user)
    try:
        data = await ApiKeywordService(session).list_paginated(owner_id, account_id.strip(), page, page_size)
        return ApiResponse(success=True, message="查询成功", data=data)
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    except SQLAlchemyError:
        logger.exception("API关键词列表查询失败: user_id={}, account={}", user_id, account_id)
        return ApiResponse(success=False, code=50001, message="查询API关键词失败，请稍后重试")


@router.post("/{account_id}", response_model=ApiResponse)
async def create_api_keyword(
    account_id: str,
    payload: Annotated[dict, Body()],
    current_user: CurrentUser,
    session: DatabaseSession,
) -> ApiResponse:
    """校验表单后真实保存，业务错误使用中文message及统一返回格式。"""
    user_id = current_user.id
    owner_id, _ = resolve_owner_scope(current_user)
    try:
        validated = ApiKeywordCreate.model_validate(payload)
        data = await ApiKeywordService(session).create(owner_id, account_id, validated)
        return ApiResponse(success=True, message="API关键词保存成功", data=data)
    except ValidationError as exc:
        logger.warning("API关键词校验失败: user_id={}, account={}, payload={}, error={}",
                       user_id, account_id, payload, exc)
        return ApiResponse(success=False, code=40001, message=_validation_message(exc))
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    except SQLAlchemyError:
        logger.exception("API关键词创建失败: user_id={}, account={}, payload={}", user_id, account_id, payload)
        return ApiResponse(success=False, code=50001, message="保存API关键词失败，请稍后重试")


@router.get("/{account_id}/{rule_id}", response_model=ApiResponse)
async def get_api_keyword_detail(
    account_id: str, rule_id: RuleId, current_user: CurrentUser, session: DatabaseSession,
) -> ApiResponse:
    """编辑前读取当前用户权限范围内的最新配置及版本。"""
    user_id = current_user.id
    owner_id, _ = resolve_owner_scope(current_user)
    try:
        data = await ApiKeywordService(session).get_detail(owner_id, account_id, rule_id)
        return ApiResponse(success=True, message="查询成功", data=data)
    except ValueError as exc:
        return ApiResponse(success=False, code=40001, message=str(exc))
    except SQLAlchemyError:
        logger.exception("API关键词详情查询失败: user_id={}, account={}, id={}", user_id, account_id, rule_id)
        return ApiResponse(success=False, code=50001, message="读取API关键词配置失败，请稍后重试")


@router.put("/{account_id}/{rule_id}", response_model=ApiResponse)
async def update_api_keyword(
    account_id: str, rule_id: RuleId, payload: Annotated[dict, Body()],
    current_user: CurrentUser, session: DatabaseSession,
) -> ApiResponse:
    """复用新建字段校验并保存原配置，业务错误统一使用HTTP200及中文提示。"""
    user_id = current_user.id
    owner_id, _ = resolve_owner_scope(current_user)
    try:
        validated = ApiKeywordUpdate.model_validate(payload)
        data = await ApiKeywordService(session).update(owner_id, account_id, rule_id, validated)
        return ApiResponse(success=True, message="API关键词修改成功", data=data)
    except ValidationError as exc:
        logger.warning("API关键词修改校验失败: user_id={}, account={}, id={}, payload={}, error={}",
                       user_id, account_id, rule_id, payload, exc)
        return ApiResponse(success=False, code=40001, message=_validation_message(exc))
    except ValueError as exc:
        return ApiResponse(success=False, code=40001, message=str(exc))
    except SQLAlchemyError:
        logger.exception("API关键词修改失败: user_id={}, account={}, id={}, payload={}", user_id, account_id, rule_id, payload)
        return ApiResponse(success=False, code=50001, message="修改API关键词失败，请稍后重试")
