"""
在线聊天(新) - 图片发送 API 路由

功能：
1. 接收前端上传的图片，先上传到闲鱼CDN，再通过IM协议发送图片消息给买家

与 chat_new.py 共用同一 prefix="/chat-new"，按功能拆分为独立 router 以控制单文件体积。
"""
from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, UploadFile
from loguru import logger
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db_session
from app.services.chat_new import get_im_session_manager
from common.models import User, XYAccount
from common.schemas.common import ApiResponse
from common.utils.auth_scope import is_admin_user
from common.utils.image_uploader import ImageUploader

router = APIRouter(prefix="/chat-new")

# 允许的图片类型与大小上限（与项目其它图片上传保持一致）
_ALLOWED_CONTENT_PREFIX = "image/"
_MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


async def _get_owned_chat_account(
    account_id: str, current_user: User, db: AsyncSession
) -> XYAccount | None:
    """校验账号归属：管理员可操作任意账号，普通用户仅能操作自己的账号"""
    query = select(XYAccount).where(XYAccount.account_id == account_id)
    if not is_admin_user(current_user):
        query = query.where(XYAccount.owner_id == current_user.id)
    return (await db.execute(query)).scalar_one_or_none()


@router.post("/send-image/{account_id}")
async def send_image(
    account_id: str,
    cid: str = Form(...),
    toUserId: str = Form(...),
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    发送图片消息

    流程：
    1. 校验账号归属与IM连接状态
    2. 校验图片类型与大小
    3. 将图片上传到闲鱼CDN，获取可访问的CDN URL
    4. 通过IM协议发送图片消息

    Args:
        account_id: 账号ID
        cid: 会话ID（不含@goofish后缀）
        toUserId: 对方用户ID
        image: 上传的图片文件
    """
    # 1. 校验归属
    if not await _get_owned_chat_account(account_id, current_user, db):
        return ApiResponse(success=False, message="账号不存在或无权操作")

    # 2. 校验连接状态
    manager = get_im_session_manager()
    client = manager.clients.get(account_id)
    if not client or not client.is_connected:
        return ApiResponse(success=False, message="账号未连接，请先连接")

    # 3. 校验图片类型
    if not image.content_type or not image.content_type.startswith(_ALLOWED_CONTENT_PREFIX):
        return ApiResponse(success=False, message="请上传图片文件")

    image_data = await image.read()
    if not image_data:
        return ApiResponse(success=False, message="上传文件为空")
    if len(image_data) > _MAX_IMAGE_SIZE:
        return ApiResponse(success=False, message="图片大小不能超过10MB")

    # 4. 落盘临时文件，读取尺寸并上传到闲鱼CDN
    temp_path = None
    try:
        suffix = os.path.splitext(image.filename or "")[1] or ".jpg"
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(image_data)

        # 读取原图尺寸，用于前端按比例渲染（失败则用默认尺寸）
        width, height = 800, 600
        try:
            with Image.open(temp_path) as img:
                width, height = img.size
        except Exception as e:
            logger.warning(f"【{account_id}】读取图片尺寸失败，使用默认尺寸: {e}")

        uploader = ImageUploader(client.cookies_str)
        async with uploader:
            cdn_url = await uploader.upload_image(temp_path)

        if not cdn_url:
            return ApiResponse(success=False, message="图片上传失败，请检查账号Cookie是否有效或稍后重试")

        # 5. 发送图片消息
        send_result = await client.send_image_message(
            cid=cid,
            to_user_id=toUserId,
            image_url=cdn_url,
            width=width,
            height=height,
        )
        logger.info(f"【{account_id}】发送图片消息到 {toUserId}: {cdn_url}")
        return ApiResponse(
            success=True,
            message="发送成功",
            data={
                "messageId": send_result.get("messageId", ""),
                "imageUrl": cdn_url,
            },
        )
    except Exception as e:
        # IM 安全拦截等业务错误会抛出明文原因，直接透传给前端展示
        logger.warning(f"【{account_id}】发送图片消息失败: {e}")
        return ApiResponse(success=False, message=f"发送失败：{str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
