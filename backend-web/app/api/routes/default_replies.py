"""默认回复管理路由"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models.user import User
from common.utils.auth_scope import resolve_owner_scope
from common.utils.local_image_upload import ImageUploadError, save_uploaded_image
from common.utils.default_reply_api import validate_api_url, normalize_api_timeout
from app.services.account_service import AccountService
from app.services.default_reply_service import DefaultReplyService

router = APIRouter(tags=["default-replies"])

# 图片上传目录 - 使用统一的静态文件根目录（兼容Docker共享卷）
from app.core.paths import STATIC_ROOT
UPLOAD_DIR = STATIC_ROOT / "uploads" / "default_reply"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class DefaultReplyUpdate(BaseModel):
    enabled: bool = False
    reply_type: str = "text"  # text-文本(可附带图片)，api-接口
    reply_content: str = ""
    reply_image: str = ""
    api_url: str = ""
    api_timeout: int = 80
    reply_once: bool = False


async def get_default_reply_service(
    session: AsyncSession = Depends(deps.get_db_session),
) -> DefaultReplyService:
    return DefaultReplyService(session)


@router.get("/{account_id}")
async def get_default_reply(
    account_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    reply_service: DefaultReplyService = Depends(get_default_reply_service),
):
    """获取指定账号的默认回复设置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    
    result = await reply_service.get_default_reply(account_id)
    if result is None:
        return {
            "enabled": False,
            "reply_type": "text",
            "reply_content": "",
            "reply_image": "",
            "api_url": "",
            "api_timeout": 80,
            "reply_once": False,
        }
    return result


@router.put("/{account_id}")
async def update_default_reply(
    account_id: str,
    reply_data: DefaultReplyUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    reply_service: DefaultReplyService = Depends(get_default_reply_service),
):
    """更新指定账号的默认回复设置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    # API 类型需校验地址合法性（防 SSRF）
    api_timeout = normalize_api_timeout(reply_data.api_timeout)
    if reply_data.reply_type == "api":
        valid, err = validate_api_url(reply_data.api_url)
        if not valid:
            return {
                "success": False,
                "message": err,
            }

    await reply_service.save_default_reply(
        account_id,
        reply_data.enabled,
        reply_data.reply_content,
        reply_data.reply_once,
        reply_data.reply_image,
        reply_type=reply_data.reply_type,
        api_url=reply_data.api_url,
        api_timeout=api_timeout,
    )
    return {
        "success": True,
        "message": "默认回复更新成功",
        "enabled": reply_data.enabled,
        "reply_once": reply_data.reply_once,
    }


@router.post("/{account_id}/upload-image")
async def upload_default_reply_image(
    account_id: str,
    image: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """上传默认回复图片"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    try:
        # 保留原行为：只校验类型，不限制文件大小
        _, filename, _ = await save_uploaded_image(
            image,
            UPLOAD_DIR,
            filename_prefix=account_id,
            validate_size=False,
        )
    except ImageUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    # 返回相对URL路径
    image_url = f"/static/uploads/default_reply/{filename}"
    return {"success": True, "image_url": image_url}


@router.get("")
async def get_all_default_replies(
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    reply_service: DefaultReplyService = Depends(get_default_reply_service),
):
    """获取当前用户所有账号的默认回复设置"""
    account_ids = await account_service.list_account_ids(current_user.id)
    
    return await reply_service.get_all_default_replies(account_ids)


@router.delete("/{account_id}")
async def delete_default_reply(
    account_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    reply_service: DefaultReplyService = Depends(get_default_reply_service),
):
    """删除指定账号的默认回复设置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    
    success = await reply_service.delete_default_reply(account_id)
    if success:
        return {"message": "默认回复删除成功"}
    raise HTTPException(status_code=400, detail="删除失败")


@router.post("/{account_id}/clear-records")
async def clear_default_reply_records(
    account_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    reply_service: DefaultReplyService = Depends(get_default_reply_service),
):
    """清空指定账号的默认回复记录"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)
    account = await account_service.get_account_for_user(owner_id, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    
    await reply_service.clear_reply_records(account_id)
    return {"message": "默认回复记录已清空"}
