from __future__ import annotations

from typing import Dict

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.api import deps
from common.models.user import User
from common.schemas.ai_reply import AIModelListRequest, AIReplySettings, AIReplySettingsUpdate
from common.schemas.common import ApiResponse
from common.services.ai_provider_service import fetch_ai_model_list, test_ai_connection
from common.utils.auth_scope import resolve_owner_scope
from app.services.account_service import AccountService
from app.services.ai_reply_service import AIReplySettingsService

router = APIRouter(tags=["ai"])
test_router = APIRouter(prefix="/ai-reply-test", tags=["ai"])


@router.get("", response_model=dict[str, AIReplySettings])
async def list_ai_reply_settings(
    current_user: User = Depends(deps.get_current_active_user),
    ai_service: AIReplySettingsService = Depends(deps.get_ai_reply_service),
) -> dict[str, AIReplySettings]:
    return await ai_service.list_settings(current_user.id)


@router.post("/models", response_model=ApiResponse)
async def fetch_ai_reply_models(
    payload: AIModelListRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> ApiResponse:
    """手动获取AI模型列表，失败时返回空列表，由前端切换为手动输入"""
    try:
        models = await fetch_ai_model_list(
            payload.provider_type,
            payload.base_url,
            payload.api_key,
        )
        if not models:
            return ApiResponse(
                success=False,
                message="该服务商未返回模型列表，请直接在文本框输入模型名称",
                data={"models": []},
            )
        return ApiResponse(success=True, message=f"获取模型列表成功，共 {len(models)} 个模型", data={"models": models})
    except (TimeoutError, httpx.TimeoutException):
        return ApiResponse(
            success=False,
            message="获取模型列表超时，请直接在文本框输入模型名称",
            data={"models": []},
        )
    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"获取模型列表失败：{e}，请直接在文本框输入模型名称",
            data={"models": []},
        )


@router.get("/{cookie_id}", response_model=AIReplySettings)
async def get_ai_reply_settings(
    cookie_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    ai_service: AIReplySettingsService = Depends(deps.get_ai_reply_service),
) -> AIReplySettings:
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    return AIReplySettings(**(await ai_service.get_settings(account)))


@router.put("/{cookie_id}", response_model=ApiResponse)
async def update_ai_reply_settings(
    cookie_id: str,
    payload: AIReplySettingsUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    ai_service: AIReplySettingsService = Depends(deps.get_ai_reply_service),
) -> ApiResponse:
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")
    try:
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            return ApiResponse(success=False, message="请至少填写一个修改项")
        await ai_service.update_settings(account, update_data)
    except ValueError as e:
        return ApiResponse(success=False, message=str(e))
    return ApiResponse(success=True, message="AI回复设置更新成功")


@router.put("", response_model=ApiResponse)
async def bulk_update_ai_settings(
    settings_map: Dict[str, AIReplySettingsUpdate] = Body(...),
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    ai_service: AIReplySettingsService = Depends(deps.get_ai_reply_service),
) -> ApiResponse:
    accounts = await account_service.list_accounts(current_user.id)
    account_lookup = {account.account_id: account for account in accounts}
    updated = 0
    for cookie_id, payload in settings_map.items():
        account = account_lookup.get(cookie_id)
        if not account:
            continue
        try:
            update_data = payload.model_dump(exclude_unset=True)
            if not update_data:
                continue
            await ai_service.update_settings(account, update_data)
        except ValueError as e:
            return ApiResponse(success=False, message=str(e))
        updated += 1
    if not updated:
        return ApiResponse(success=False, message="未找到任何可更新的账号")
    return ApiResponse(success=True, message=f"已更新 {updated} 个账号的AI回复设置")


@test_router.post("/{cookie_id}", response_model=ApiResponse)
async def test_ai_reply_settings(
    cookie_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    ai_service: AIReplySettingsService = Depends(deps.get_ai_reply_service),
) -> ApiResponse:
    """测试AI连接是否正常"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    
    # 获取该账号的AI设置
    settings = await ai_service.get_settings(account)
    api_key = settings.get("api_key", "")
    provider_type = settings.get("provider_type", "openai_compatible")
    base_url = settings.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model_name = settings.get("model_name", "qwen-plus")
    
    try:
        reply = await test_ai_connection(provider_type, base_url, api_key, model_name)
        return ApiResponse(success=True, message=f"AI连接测试成功！模型回复: {reply[:100]}")
    except (TimeoutError, httpx.TimeoutException):
        return ApiResponse(success=False, message="AI连接超时，请检查网络或API地址")
    except Exception as e:
        return ApiResponse(success=False, message=f"AI连接测试失败: {str(e)}")
