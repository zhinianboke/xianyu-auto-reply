from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.auth_scope import resolve_owner_scope
from common.utils.default_reply_api import validate_api_url, normalize_api_timeout
from common.schemas.item import (
    ItemBatchDeleteRequest,
    ItemBatchOfflineRequest,
    ItemFullFetchRequest,
    ItemPageFetchRequest,
)
from common.services.item_offline_service import batch_offline_items_from_xianyu
from common.services.item_delete_service import batch_delete_items_from_xianyu
from app.services.account_service import AccountService
from app.services.item_service import ItemService
from app.services.selectable_item_service import SelectableItemService

logger = logging.getLogger(__name__)

items_router = APIRouter(prefix="/items", tags=["items"])


async def _execute_batch_item_operation(
    *,
    item_ids: List[str],
    operation: Callable[[str], Awaitable[Any]],
    action_verb: str,
    subject: str,
) -> ApiResponse:
    """对一批商品执行同一个操作，统一处理 成功/失败 计数与响应文案。

    4 个商品批量接口 (``batch_save_item_default_reply`` /
    ``batch_delete_item_default_reply`` / ``batch_delete_item_ai_prompt`` /
    ``batch_save_item_ai_prompt``) 共用此 helper，避免重复书写
    “计数循环 + 三分支消息组装 + 外层 try/except”的模板代码。

    Args:
        item_ids: 待处理的商品 ID 列表。
        operation: 对单个 ``item_id`` 的异步操作；返回真值视为成功，
            返回假值或抛出异常视为失败（与原 4 处实现一致）。
        action_verb: 中文动词（“保存” / “删除”），用于组装日志与提示文案。
        subject: 操作主体（“默认回复” / “AI提示词”），用于组装日志与提示文案。

    Returns:
        ``ApiResponse``：
          - 全部成功: ``success=True, message="已成功{动词} N 个商品的{主体}"``
          - 部分成功: ``success=True, message="已{动词} N 个商品，M 个失败"``
          - 全部失败: ``success=False, message="{动词}失败"``
          - 整体异常: ``success=False, message="{动词}失败: <异常>"``
    """
    try:
        success_count = 0
        fail_count = 0

        for item_id in item_ids:
            try:
                result = await operation(item_id)
                if result:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as exc:
                logger.error(f"{action_verb}商品 {item_id} {subject}失败: {exc}")
                fail_count += 1

        if fail_count == 0:
            return ApiResponse(
                success=True,
                message=f"已成功{action_verb} {success_count} 个商品的{subject}",
            )
        if success_count > 0:
            return ApiResponse(
                success=True,
                message=f"已{action_verb} {success_count} 个商品，{fail_count} 个失败",
            )
        return ApiResponse(success=False, message=f"{action_verb}失败")
    except Exception as exc:
        logger.error(f"批量{action_verb}商品{subject}失败: {exc}")
        return ApiResponse(success=False, message=f"{action_verb}失败: {exc}")


@items_router.get("")
async def list_items(
    current_user: User = Depends(deps.get_current_active_user),
    item_service: ItemService = Depends(deps.get_item_service),
) -> Dict[str, List[dict]]:
    """获取商品列表，管理员可查看所有商品"""
    owner_id, _ = resolve_owner_scope(current_user)
    items = await item_service.list_items(owner_id)
    return {"items": items}


@items_router.get("/paginated")
async def list_items_paginated(
    cookie_id: str | None = Query(default=None, description="账号ID"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    keyword: str | None = Query(default=None, description="关键字（支持商品ID、标题、详情）"),
    is_polished: bool | None = Query(default=None, description="是否擦亮筛选"),
    is_multi_spec: bool | None = Query(default=None, description="多规格筛选"),
    multi_quantity_delivery: bool | None = Query(default=None, description="多数量发货筛选"),
    current_user: User = Depends(deps.get_current_active_user),
    item_service: ItemService = Depends(deps.get_item_service),
):
    """获取商品列表（分页），支持多条件筛选
    
    管理员可查看所有商品。
    
    筛选条件：
    - keyword: 关键字（商品ID、标题、详情）
    - is_polished: 是否擦亮（true/false）
    - is_multi_spec: 多规格（true/false）
    - multi_quantity_delivery: 多数量发货（true/false）
    """
    owner_id, _ = resolve_owner_scope(current_user)
    items, total = await item_service.list_items_paginated(
        owner_id=owner_id,
        account_id=cookie_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        is_polished=is_polished,
        is_multi_spec=is_multi_spec,
        multi_quantity_delivery=multi_quantity_delivery,
    )
    
    return {
        "success": True,
        "data": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@items_router.get("/selectable/all")
async def list_selectable_items_all(
    keyword: str | None = Query(default=None, max_length=255, description="关键字（商品ID/标题）"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """卡券关联商品选择弹窗：获取全部匹配的可选商品轻量项（供「全选筛选结果」）

    仅返回 item_id/title/price 轻字段，管理员可查看所有商品。
    """
    owner_id, _ = resolve_owner_scope(current_user)
    items = await SelectableItemService(session).get_all_selectable_item_keys(
        owner_id=owner_id,
        search=keyword or "",
    )
    return {"list": items, "total": len(items)}


@items_router.get("/by-card/{card_id}")
async def list_items_by_card(
    card_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """卡券关联商品选择弹窗：获取卡券已关联商品的轻量详情（供右侧「已选商品」展示）

    仅返回 item_id/title/price；已删除商品不在此返回，选中态由
    GET /cards/{card_id}/items 提供，保存时不丢失。
    """
    owner_id, _ = resolve_owner_scope(current_user)
    items = await SelectableItemService(session).get_associated_items(
        card_id=card_id,
        owner_id=owner_id,
    )
    return {"list": items, "total": len(items)}


@items_router.get("/cookie/{cookie_id}")
async def list_items_by_cookie(
    cookie_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> Dict[str, List[dict]]:
    """获取指定账号的商品列表，管理员可查看所有账号"""
    owner_id, is_admin = resolve_owner_scope(current_user)

    if is_admin:
        account = await account_service.get_account_by_identifier(cookie_id)
    else:
        account = await account_service.get_account_for_user(current_user.id, cookie_id)

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    items = await item_service.list_items(owner_id, cookie_id)
    return {"items": items}


# ==================== 商品默认回复（必须在 /{cookie_id}/{item_id} 之前定义）====================

from pydantic import BaseModel as PydanticBaseModel


class ItemDefaultReplyRequest(PydanticBaseModel):
    """商品默认回复请求"""
    reply_content: str
    reply_image: str = ""
    enabled: bool = True
    reply_once: bool = False
    reply_type: str = "text"  # text-文本(可附带图片)，api-接口
    api_url: str = ""
    api_timeout: int = 80


@items_router.get("/{cookie_id}/{item_id}/default-reply")
async def get_item_default_reply(
    cookie_id: str,
    item_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    default_reply_service: DefaultReplyService = Depends(deps.get_default_reply_service),
) -> ApiResponse:
    """获取商品默认回复配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")
    
    try:
        reply_config = await default_reply_service.get_item_default_reply(cookie_id, item_id)
        
        if reply_config:
            return ApiResponse(
                success=True,
                message="获取成功",
                data={
                    "item_id": item_id,
                    "reply_content": reply_config.get("reply_content", ""),
                    "reply_image": reply_config.get("reply_image", ""),
                    "enabled": reply_config.get("enabled", False),
                    "reply_once": reply_config.get("reply_once", False),
                    "reply_type": reply_config.get("reply_type", "text"),
                    "api_url": reply_config.get("api_url", ""),
                    "api_timeout": reply_config.get("api_timeout", 80),
                }
            )
        else:
            return ApiResponse(
                success=True,
                message="未配置商品默认回复",
                data={
                    "item_id": item_id,
                    "reply_content": "",
                    "reply_image": "",
                    "enabled": False,
                    "reply_once": False,
                    "reply_type": "text",
                    "api_url": "",
                    "api_timeout": 80,
                }
            )
    except Exception as e:
        logger.error(f"获取商品默认回复失败: {e}")
        return ApiResponse(success=False, message=f"获取失败: {str(e)}")


@items_router.put("/{cookie_id}/{item_id}/default-reply", response_model=ApiResponse)
async def save_item_default_reply(
    cookie_id: str,
    item_id: str,
    payload: ItemDefaultReplyRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    default_reply_service: DefaultReplyService = Depends(deps.get_default_reply_service),
) -> ApiResponse:
    """保存商品默认回复配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")
    
    # API 类型需校验地址合法性（防 SSRF）
    api_timeout = normalize_api_timeout(payload.api_timeout)
    if payload.reply_type == "api":
        valid, err = validate_api_url(payload.api_url)
        if not valid:
            return ApiResponse(success=False, message=err)

    try:
        success = await default_reply_service.save_item_default_reply(
            account_id=cookie_id,
            item_id=item_id,
            reply_content=payload.reply_content,
            reply_image=payload.reply_image,
            enabled=payload.enabled,
            reply_once=payload.reply_once,
            reply_type=payload.reply_type,
            api_url=payload.api_url,
            api_timeout=api_timeout,
        )
        
        if success:
            return ApiResponse(success=True, message="商品默认回复已保存")
        else:
            return ApiResponse(success=False, message="保存失败")
    except Exception as e:
        logger.error(f"保存商品默认回复失败: {e}")
        return ApiResponse(success=False, message=f"保存失败: {str(e)}")


from fastapi import File, UploadFile

from common.utils.local_image_upload import ImageUploadError, save_uploaded_image

# 图片上传目录 - 使用统一的静态文件根目录（兼容Docker共享卷）
from app.core.paths import STATIC_ROOT
ITEM_REPLY_UPLOAD_DIR = STATIC_ROOT / "uploads" / "item_reply"
ITEM_REPLY_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@items_router.post("/{cookie_id}/{item_id}/default-reply/upload-image")
async def upload_item_default_reply_image(
    cookie_id: str,
    item_id: str,
    image: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """上传商品默认回复图片"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")

    try:
        # 保留原行为：只校验类型，不限制文件大小
        _, filename, _ = await save_uploaded_image(
            image,
            ITEM_REPLY_UPLOAD_DIR,
            filename_prefix=f"{cookie_id}_{item_id}",
            validate_size=False,
        )
    except ImageUploadError as exc:
        return ApiResponse(success=False, message=exc.message)

    # 返回相对URL路径
    image_url = f"/static/uploads/item_reply/{filename}"
    return {"success": True, "image_url": image_url}


@items_router.delete("/{cookie_id}/{item_id}/default-reply", response_model=ApiResponse)
async def delete_item_default_reply(
    cookie_id: str,
    item_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    default_reply_service: DefaultReplyService = Depends(deps.get_default_reply_service),
) -> ApiResponse:
    """删除商品默认回复配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")
    
    try:
        success = await default_reply_service.delete_item_default_reply(cookie_id, item_id)
        
        if success:
            return ApiResponse(success=True, message="商品默认回复已删除")
        else:
            return ApiResponse(success=False, message="删除失败")
    except Exception as e:
        logger.error(f"删除商品默认回复失败: {e}")
        return ApiResponse(success=False, message=f"删除失败: {str(e)}")


class BatchItemDefaultReplyRequest(PydanticBaseModel):
    """批量商品默认回复请求"""
    item_ids: List[str]
    reply_content: str
    reply_image: str = ""
    enabled: bool = True
    reply_once: bool = False
    reply_type: str = "text"  # text-文本(可附带图片)，api-接口
    api_url: str = ""
    api_timeout: int = 80


@items_router.post("/{cookie_id}/batch-default-reply/upload-image")
async def upload_batch_default_reply_image(
    cookie_id: str,
    image: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """上传批量默认回复图片"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")

    try:
        # 保留原行为：只校验类型，不限制文件大小
        _, filename, _ = await save_uploaded_image(
            image,
            ITEM_REPLY_UPLOAD_DIR,
            filename_prefix=f"{cookie_id}_batch",
            validate_size=False,
        )
    except ImageUploadError as exc:
        return ApiResponse(success=False, message=exc.message)

    # 返回相对URL路径
    image_url = f"/static/uploads/item_reply/{filename}"
    return {"success": True, "image_url": image_url}


@items_router.post("/{cookie_id}/batch-default-reply", response_model=ApiResponse)
async def batch_save_item_default_reply(
    cookie_id: str,
    payload: BatchItemDefaultReplyRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    default_reply_service: DefaultReplyService = Depends(deps.get_default_reply_service),
) -> ApiResponse:
    """批量保存商品默认回复配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")
    
    if not payload.item_ids:
        return ApiResponse(success=False, message="请选择至少一个商品")

    # API 类型需校验地址合法性（防 SSRF）
    api_timeout = normalize_api_timeout(payload.api_timeout)
    if payload.reply_type == "api":
        valid, err = validate_api_url(payload.api_url)
        if not valid:
            return ApiResponse(success=False, message=err)

    return await _execute_batch_item_operation(
        item_ids=payload.item_ids,
        operation=lambda item_id: default_reply_service.save_item_default_reply(
            account_id=cookie_id,
            item_id=item_id,
            reply_content=payload.reply_content,
            reply_image=payload.reply_image,
            enabled=payload.enabled,
            reply_once=payload.reply_once,
            reply_type=payload.reply_type,
            api_url=payload.api_url,
            api_timeout=api_timeout,
        ),
        action_verb="保存",
        subject="默认回复",
    )


class BatchDeleteDefaultReplyRequest(PydanticBaseModel):
    """批量删除商品默认回复请求"""
    item_ids: List[str]


@items_router.post("/{cookie_id}/batch-delete-default-reply", response_model=ApiResponse)
async def batch_delete_item_default_reply(
    cookie_id: str,
    payload: BatchDeleteDefaultReplyRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    default_reply_service: DefaultReplyService = Depends(deps.get_default_reply_service),
) -> ApiResponse:
    """批量删除商品默认回复配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")
    
    if not payload.item_ids:
        return ApiResponse(success=False, message="请选择至少一个商品")

    return await _execute_batch_item_operation(
        item_ids=payload.item_ids,
        operation=lambda item_id: default_reply_service.delete_item_default_reply(cookie_id, item_id),
        action_verb="删除",
        subject="默认回复",
    )


# ==================== 商品AI提示词 ====================


class ItemAiPromptRequest(PydanticBaseModel):
    """商品AI提示词请求"""
    ai_prompt: str


@items_router.get("/{cookie_id}/{item_id}/ai-prompt")
async def get_item_ai_prompt(
    cookie_id: str,
    item_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> ApiResponse:
    """获取商品AI提示词配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")
    
    try:
        item = await item_service.get_item(owner_id, cookie_id, item_id)
        if not item:
            return ApiResponse(success=False, message="商品不存在")
        
        return ApiResponse(
            success=True,
            message="获取成功",
            data={
                "item_id": item_id,
                "ai_prompt": item.get("ai_prompt", "") or "",
            }
        )
    except Exception as e:
        logger.error(f"获取商品AI提示词失败: {e}")
        return ApiResponse(success=False, message=f"获取失败: {str(e)}")


@items_router.put("/{cookie_id}/{item_id}/ai-prompt", response_model=ApiResponse)
async def save_item_ai_prompt(
    cookie_id: str,
    item_id: str,
    payload: ItemAiPromptRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> ApiResponse:
    """保存商品AI提示词配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")
    
    try:
        updated = await item_service.update_item(account, item_id, {"ai_prompt": payload.ai_prompt})
        if updated:
            return ApiResponse(success=True, message="商品AI提示词已保存")
        else:
            return ApiResponse(success=False, message="商品不存在")
    except Exception as e:
        logger.error(f"保存商品AI提示词失败: {e}")
        return ApiResponse(success=False, message=f"保存失败: {str(e)}")


class BatchDeleteAiPromptRequest(PydanticBaseModel):
    """批量删除商品AI提示词请求"""
    item_ids: List[str]


@items_router.post("/{cookie_id}/batch-delete-ai-prompt", response_model=ApiResponse)
async def batch_delete_item_ai_prompt(
    cookie_id: str,
    payload: BatchDeleteAiPromptRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> ApiResponse:
    """批量删除商品AI提示词配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")
    
    if not payload.item_ids:
        return ApiResponse(success=False, message="请选择至少一个商品")
    
    return await _execute_batch_item_operation(
        item_ids=payload.item_ids,
        operation=lambda item_id: item_service.update_item(account, item_id, {"ai_prompt": ""}),
        action_verb="删除",
        subject="AI提示词",
    )


class BatchSaveAiPromptRequest(PydanticBaseModel):
    """批量保存商品AI提示词请求"""
    item_ids: List[str]
    ai_prompt: str


@items_router.post("/{cookie_id}/batch-ai-prompt", response_model=ApiResponse)
async def batch_save_item_ai_prompt(
    cookie_id: str,
    payload: BatchSaveAiPromptRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> ApiResponse:
    """批量保存商品AI提示词配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")
    
    if not payload.item_ids:
        return ApiResponse(success=False, message="请选择至少一个商品")
    
    return await _execute_batch_item_operation(
        item_ids=payload.item_ids,
        operation=lambda item_id: item_service.update_item(account, item_id, {"ai_prompt": payload.ai_prompt}),
        action_verb="保存",
        subject="AI提示词",
    )


# ==================== 商品详情（通用路由放在具体路由之后）====================

@items_router.get("/{cookie_id}/{item_id}")
async def get_item_detail(
    cookie_id: str,
    item_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> Dict[str, dict]:
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    item = await item_service.get_item(owner_id, cookie_id, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商品不存在")
    return {"item": item}


@items_router.put("/{cookie_id}/{item_id}", response_model=ApiResponse)
async def update_item(
    cookie_id: str,
    item_id: str,
    payload: dict,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> ApiResponse:
    """更新商品信息"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    logger.info(f"更新商品: cookie_id={cookie_id}, item_id={item_id}, payload={payload}")
    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    updated = await item_service.update_item(account, item_id, payload)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商品不存在")
    logger.info(f"商品更新成功: item_id={item_id}")
    return ApiResponse(success=True, message="商品已更新")


@items_router.put("/{cookie_id}/{item_id}/multi-spec", response_model=ApiResponse)
async def update_item_multi_spec(
    cookie_id: str,
    item_id: str,
    payload: dict,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> ApiResponse:
    """更新商品的多规格状态"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    is_multi_spec = payload.get("is_multi_spec", False)
    updated = await item_service.update_item(account, item_id, {"is_multi_spec": is_multi_spec})
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商品不存在")
    status_text = "开启" if is_multi_spec else "关闭"
    return ApiResponse(success=True, message=f"商品多规格状态已{status_text}")


@items_router.put("/{cookie_id}/{item_id}/multi-quantity-delivery", response_model=ApiResponse)
async def update_item_multi_quantity_delivery(
    cookie_id: str,
    item_id: str,
    payload: dict,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> ApiResponse:
    """更新商品的多数量发货状态"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    multi_quantity_delivery = payload.get("multi_quantity_delivery", False)
    updated = await item_service.update_item(account, item_id, {"multi_quantity_delivery": multi_quantity_delivery})
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商品不存在")
    status_text = "开启" if multi_quantity_delivery else "关闭"
    return ApiResponse(success=True, message=f"商品多数量发货状态已{status_text}")


class ItemDeleteRequest(PydanticBaseModel):
    """统一删除商品请求（账号可选）

    - cookie_id 传入：按账号删除（校验归属）；
    - cookie_id 不传：商品所属账号仍存在则要求指定账号，账号已删除（孤儿商品）则直接按商品ID删除。
    """
    item_id: str
    cookie_id: str | None = None


@items_router.delete("/delete", response_model=ApiResponse)
async def delete_item_unified(
    payload: ItemDeleteRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> ApiResponse:
    """删除商品（统一入口，账号可选，兼容账号已删除的孤儿商品）

    - 传入 cookie_id：校验账号归属后按账号删除；账号不存在直接报错。
    - 未传 cookie_id：若商品所属账号仍存在则要求指定账号；账号已删除（孤儿商品）则按商品ID删除。
    """
    owner_id, _ = resolve_owner_scope(current_user)

    account = None
    # 将 "null"、空字符串等无效值统一视为未传入 cookie_id
    cookie_id = payload.cookie_id
    if cookie_id and cookie_id.lower() not in ("null", ""):
        account = await account_service.get_account_for_user(owner_id, cookie_id)
        if not account:
            return ApiResponse(success=False, message="账号不存在")

    result = await item_service.delete_item_smart(owner_id, payload.item_id, account)
    if result == "ok":
        return ApiResponse(success=True, message="商品已删除")
    if result == "account_required":
        return ApiResponse(success=False, message="该商品所属账号仍存在，请指定账号后再删除")
    return ApiResponse(success=False, message="商品不存在")


@items_router.delete("/{cookie_id}/{item_id}", response_model=ApiResponse)
async def delete_item(
    cookie_id: str,
    item_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> ApiResponse:
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    deleted = await item_service.delete_item(account, item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商品不存在")
    return ApiResponse(success=True, message="商品已删除")


@items_router.delete("/batch", response_model=ApiResponse)
async def batch_delete_items(
    payload: ItemBatchDeleteRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> ApiResponse:
    from loguru import logger

    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    accounts = await account_service.list_accounts(owner_id)
    account_map = {account.account_id: account for account in accounts}
    removed = 0
    not_found_items = []
    for entry in payload.items:
        # 将 "null"、空字符串等无效 cookie_id 视为未指定账号（孤儿商品场景）
        cookie_id = entry.cookie_id
        account = None
        if cookie_id and cookie_id.lower() not in ("null", ""):
            account = account_map.get(cookie_id)

        # 使用 delete_item_smart 统一处理，兼容孤儿商品
        result = await item_service.delete_item_smart(owner_id, entry.item_id, account)
        if result == "ok":
            removed += 1
        else:
            not_found_items.append(entry.item_id)
    logger.info(f"批量删除商品: 请求={len(payload.items)}, 成功={removed}, 商品未找到={not_found_items}")
    if removed == 0 and len(payload.items) > 0:
        return ApiResponse(success=False, message=f"未能删除任何商品（共 {len(payload.items)} 个），请检查商品是否存在")
    return ApiResponse(success=True, message=f"已删除 {removed} 个商品")


@items_router.post("/batch-offline", response_model=ApiResponse)
async def batch_offline_items(
    payload: ItemBatchOfflineRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
) -> ApiResponse:
    """批量下架商品（调用闲鱼接口，使用所选账号的Cookie）

    下架 ≠ 删除：商品在卖家后台下架后仍可重新上架，本接口不改动本地商品库记录。
    所选账号必须是这些商品的归属账号，否则闲鱼会对不属于该账号的商品返回失败。
    """
    # 管理员可操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    if not payload.item_ids:
        return ApiResponse(success=False, message="请选择要下架的商品")

    account = await account_service.get_account_for_user(owner_id, payload.cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")
    if not account.cookie:
        return ApiResponse(success=False, message="该账号未登录（Cookie为空），无法下架")

    result = await batch_offline_items_from_xianyu(
        account.account_id, account.cookie, payload.item_ids
    )
    suc_count = result.get("suc_count", 0)
    fail_count = result.get("fail_count", 0)
    logger.info(
        f"批量下架商品: 账号={account.account_id}, 请求={len(payload.item_ids)}, "
        f"成功={suc_count}, 失败={fail_count}"
    )

    data = {"results": result.get("results", []), "suc_count": suc_count, "fail_count": fail_count}
    # 全部失败：透传闲鱼返回的失败原因，便于前端展示
    if suc_count == 0:
        return ApiResponse(
            success=False,
            message=result.get("message") or "下架失败",
            data=data,
        )
    # 部分/全部成功
    message = f"已下架 {suc_count} 个商品" + (f"，{fail_count} 个失败" if fail_count else "")
    return ApiResponse(success=True, message=message, data=data)


@items_router.post("/batch-delete-xianyu", response_model=ApiResponse)
async def batch_delete_xianyu_items(
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> ApiResponse:
    """使用指定账号 Cookie 批量删除闲鱼平台商品。

    本接口只删除闲鱼平台商品，不物理删除本地商品及关联数据。
    """
    owner_id, _ = resolve_owner_scope(current_user)
    try:
        payload = await request.json()
    except Exception as exc:
        logger.warning(
            f"批量删除闲鱼商品请求体解析失败: {type(exc).__name__}: {exc}"
        )
        return ApiResponse(success=False, message="请求体不是有效的JSON格式")
    if not isinstance(payload, dict):
        return ApiResponse(success=False, message="请求参数必须是JSON对象")

    raw_item_ids = payload.get("item_ids")
    if not isinstance(raw_item_ids, list):
        return ApiResponse(success=False, message="商品ID列表格式错误")
    invalid_item_id_index = next(
        (
            index
            for index, raw_item_id in enumerate(raw_item_ids)
            if not isinstance(raw_item_id, str)
        ),
        None,
    )
    if invalid_item_id_index is not None:
        return ApiResponse(
            success=False,
            message=f"第 {invalid_item_id_index + 1} 个商品ID格式错误",
        )

    cleaned_item_ids = list(
        dict.fromkeys(
            item_id
            for raw_item_id in raw_item_ids
            if (item_id := str(raw_item_id or "").strip())
        )
    )
    if not cleaned_item_ids:
        return ApiResponse(success=False, message="请选择要删除的闲鱼商品")
    if len(cleaned_item_ids) > 100:
        return ApiResponse(success=False, message="单次最多删除 100 个闲鱼商品")

    raw_cookie_id = payload.get("cookie_id")
    if raw_cookie_id is not None and not isinstance(raw_cookie_id, str):
        return ApiResponse(success=False, message="闲鱼账号ID格式错误")
    cookie_id = str(raw_cookie_id or "").strip()
    if not cookie_id:
        return ApiResponse(success=False, message="请选择用于删除商品的闲鱼账号")

    try:
        account = await account_service.get_account_for_user(owner_id, cookie_id)
    except Exception as exc:
        logger.error(
            f"批量删除闲鱼商品查询账号失败: cookie_id={cookie_id}, "
            f"error={type(exc).__name__}: {exc}"
        )
        return ApiResponse(
            success=False,
            message=f"查询闲鱼账号失败，请检查数据库连接（{type(exc).__name__}）",
        )
    if not account:
        return ApiResponse(success=False, message="账号不存在或无权操作")
    if not account.cookie:
        return ApiResponse(
            success=False,
            message="该账号未登录（Cookie为空），无法删除闲鱼商品",
        )

    try:
        existing_item_ids = await item_service.get_existing_item_ids_for_account(
            account,
            cleaned_item_ids,
        )
    except Exception as exc:
        logger.error(
            f"批量删除闲鱼商品校验归属失败: account_id={account.account_id}, "
            f"item_count={len(cleaned_item_ids)}, error={type(exc).__name__}: {exc}"
        )
        return ApiResponse(
            success=False,
            message=f"校验商品归属失败，请检查数据库连接（{type(exc).__name__}）",
        )
    invalid_item_ids = [
        item_id for item_id in cleaned_item_ids if item_id not in existing_item_ids
    ]
    if invalid_item_ids:
        preview = "、".join(invalid_item_ids[:5])
        suffix = f" 等 {len(invalid_item_ids)} 个" if len(invalid_item_ids) > 5 else ""
        return ApiResponse(
            success=False,
            message=f"以下商品不属于所选账号或本地记录不存在：{preview}{suffix}",
        )

    result = await batch_delete_items_from_xianyu(
        account_id=account.account_id,
        account_row_id=int(account.id),
        owner_id=int(account.owner_id),
        cookies_str=account.cookie,
        item_ids=cleaned_item_ids,
    )
    success_count = int(result.get("success_count", 0) or 0)
    fail_count = int(result.get("fail_count", 0) or 0)
    data = {
        "results": result.get("results", []),
        "success_count": success_count,
        "fail_count": fail_count,
    }
    logger.info(
        f"批量删除闲鱼商品: 账号={account.account_id}, 请求={len(cleaned_item_ids)}, "
        f"成功={success_count}, 失败={fail_count}"
    )
    if success_count == 0:
        return ApiResponse(
            success=False,
            message=result.get("message") or "删除闲鱼商品失败",
            data=data,
        )
    return ApiResponse(
        success=True,
        message=result.get("message") or f"已删除 {success_count} 个闲鱼商品",
        data=data,
    )


@items_router.post("/get-by-page")
async def fetch_items_from_account(
    payload: ItemPageFetchRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> Dict[str, Any]:
    """从闲鱼API获取指定页的商品列表"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, payload.cookie_id)
    if not account:
        return ApiResponse(success=False, message="account not found")

    page = payload.page or payload.page_number or 1
    size = payload.page_size or payload.size or 20
    try:
        page = int(page)
        size = int(size)
    except (TypeError, ValueError):
        return ApiResponse(success=False, message="page and page_size must be integers")

    if page < 1:
        return ApiResponse(success=False, message="page must be greater than 0")
    if size < 1 or size > 100:
        return ApiResponse(success=False, message="page_size must be between 1 and 100")

    return await item_service.fetch_items_page_from_account(
        account=account,
        page=page,
        page_size=size,
    )


@items_router.post("/get-all-from-account")
async def fetch_all_items_from_account(
    payload: ItemFullFetchRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    item_service: ItemService = Depends(deps.get_item_service),
) -> Dict[str, Any]:
    """获取账号所有商品（自动遍历所有页）"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    page_size = payload.page_size or 20
    max_pages = payload.max_pages
    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        return ApiResponse(success=False, message="page_size必须是整数")
    if page_size < 1 or page_size > 100:
        return ApiResponse(success=False, message="page_size必须在1-100之间")
    if max_pages is not None:
        try:
            max_pages = int(max_pages)
        except (TypeError, ValueError):
            return ApiResponse(success=False, message="max_pages必须是整数")
        if max_pages < 1:
            return ApiResponse(success=False, message="max_pages必须大于0")

    if payload.cookie_id:
        account = await account_service.get_account_for_user(owner_id, payload.cookie_id)
        if not account:
            return ApiResponse(success=False, message="账号不存在")

        return await item_service.fetch_all_items_from_account(
            account=account,
            page_size=page_size,
            max_pages=max_pages,
        )

    accounts = await account_service.list_accounts(owner_id)
    return await item_service.fetch_all_items_from_accounts(
        accounts=accounts,
        page_size=page_size,
        max_pages=max_pages,
    )

# ==================== 商品搜索 ====================


class ItemSearchRequest(PydanticBaseModel):
    """商品搜索请求"""
    keyword: str
    page: int = 1
    page_size: int = 20


@items_router.post("/search")
async def search_items(
    payload: ItemSearchRequest,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> Dict[str, Any]:
    """
    搜索闲鱼商品
    
    使用Playwright进行商品搜索
    """
    try:
        from app.services.search.searcher import ItemSearchService

        service = ItemSearchService(db_session=session, user_id=str(current_user.id))
        result = await service.search_items(
            keyword=payload.keyword,
            page=payload.page,
            page_size=payload.page_size,
        )

        if result.get("error"):
            return {"success": False, "data": [], "error": result.get("error")}

        return {"success": True, "data": result.get("items", []), "total": result.get("total", 0)}
    except Exception as e:
        logger.error(f"商品搜索失败: {e}")
        return {
            "success": False,
            "data": [],
            "error": str(e),
        }
