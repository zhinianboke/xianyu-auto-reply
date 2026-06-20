"""
用户设置 API 路由

提供用户个人设置的管理功能
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.services.card_dock_service import CARD_SECRET_KEY_SETTING, CardDockService
from app.services.card_secret_key_service import CardSecretKeyService
from common.models.user import User
from common.models.user_setting import UserSetting
from common.schemas.common import ApiResponse
from common.utils.image_utils import image_manager

from common.utils.time_utils import safe_isoformat
router = APIRouter(tags=["用户设置"])


class UserSettingUpdate(BaseModel):
    """用户设置更新请求"""
    value: str
    description: Optional[str] = None


@router.get("")
async def get_user_settings(
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> Dict[str, Any]:
    """获取当前用户的所有设置"""
    stmt = select(UserSetting).where(UserSetting.user_id == current_user.id)
    result = await session.execute(stmt)
    settings = result.scalars().all()
    
    return {
        setting.key: {
            "value": setting.value,
            "description": setting.description,
            "updated_at": safe_isoformat(setting.updated_at),
        }
        for setting in settings
    }


@router.get("/{key}")
async def get_user_setting(
    key: str,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> Dict[str, Any]:
    """获取用户特定设置，不存在时返回空值而非404"""
    stmt = select(UserSetting).where(
        UserSetting.user_id == current_user.id,
        UserSetting.key == key,
    )
    result = await session.execute(stmt)
    setting = result.scalar_one_or_none()
    
    if not setting:
        return {
            "success": True,
            "key": key,
            "value": "",
            "description": "",
        }
    
    return {
        "success": True,
        "key": setting.key,
        "value": setting.value,
        "description": setting.description,
    }


@router.put("/{key}", response_model=ApiResponse)
async def update_user_setting(
    key: str,
    payload: UserSettingUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """更新用户设置"""
    stmt = select(UserSetting).where(
        UserSetting.user_id == current_user.id,
        UserSetting.key == key,
    )
    result = await session.execute(stmt)
    setting = result.scalar_one_or_none()
    
    if setting:
        # 更新现有设置
        setting.value = payload.value
        if payload.description is not None:
            setting.description = payload.description
    else:
        # 创建新设置
        setting = UserSetting(
            user_id=current_user.id,
            key=key,
            value=payload.value,
            description=payload.description,
        )
        session.add(setting)
    
    await session.commit()

    # 对接卡密秘钥更新后立即失效缓存，避免最长 5 分钟内仍使用旧秘钥（含首次配置由空串变为有效值的场景）
    if key == CARD_SECRET_KEY_SETTING:
        CardDockService.invalidate_secret_key_cache(current_user.id)

    return ApiResponse(success=True, message="设置已保存")


@router.delete("/{key}", response_model=ApiResponse)
async def delete_user_setting(
    key: str,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """删除用户设置"""
    stmt = delete(UserSetting).where(
        UserSetting.user_id == current_user.id,
        UserSetting.key == key,
    )
    result = await session.execute(stmt)
    await session.commit()

    # 对接卡密秘钥删除后同步失效缓存
    if key == CARD_SECRET_KEY_SETTING:
        CardDockService.invalidate_secret_key_cache(current_user.id)

    return ApiResponse(success=True, message="设置已删除")


@router.post("/card-secret-key/create", response_model=ApiResponse)
async def create_card_secret_key(
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """一键创建对接卡密秘钥：调用外部密钥服务创建后，自动保存到当前用户设置。

    key_name 取「xy_ + 当前用户名」，创建成功后将返回的 key_value 写入用户设置
    distribution.card_secret_key 并失效缓存。业务错误以 HTTP 200 携带 success=False 返回。

    校验：若当前用户已存在对接卡密秘钥，则禁止重复创建，提示联系管理员重置。
    """
    # 1. 先校验是否已存在对接卡密秘钥，已存在则禁止创建
    stmt = select(UserSetting).where(
        UserSetting.user_id == current_user.id,
        UserSetting.key == CARD_SECRET_KEY_SETTING,
    )
    db_result = await session.execute(stmt)
    setting = db_result.scalar_one_or_none()
    if setting and setting.value and setting.value.strip():
        return ApiResponse(success=False, message="对接卡密秘钥已存在，如需重新创建请联系管理员重置")

    # 2. 调用外部密钥服务创建
    service = CardSecretKeyService()
    result = await service.create_key(current_user.username)
    if not result.get("success"):
        return ApiResponse(success=False, message=result.get("message") or "创建密钥失败")

    key_value = (result.get("data") or {}).get("key_value", "").strip()
    if not key_value:
        return ApiResponse(success=False, message="创建密钥成功但未返回密钥值")

    # 3. 保存到当前用户的「对接卡密秘钥」设置（存在空值记录则更新，不存在则新增）
    if setting:
        setting.value = key_value
    else:
        session.add(UserSetting(
            user_id=current_user.id,
            key=CARD_SECRET_KEY_SETTING,
            value=key_value,
            description="对接卡密秘钥",
        ))
    await session.commit()

    # 更新后立即失效缓存，避免最长 5 分钟内仍使用旧秘钥
    CardDockService.invalidate_secret_key_cache(current_user.id)

    return ApiResponse(success=True, message="对接卡密秘钥创建成功", data={"key_value": key_value})


@router.post("/payment-qrcode/upload")
async def upload_payment_qrcode(
    file: UploadFile = File(...),
    payment_type: str = Form(..., description="收款方式：alipay-支付宝，wechat-微信"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """上传或更换收款码图片，同时保存收款方式"""
    if payment_type not in ('alipay', 'wechat'):
        return {'success': False, 'message': '收款方式无效，必须是 alipay 或 wechat'}

    image_data = await file.read()
    if not image_data:
        return {'success': False, 'message': '上传文件为空'}

    image_url = image_manager.save_image(image_data, file.filename)
    if not image_url:
        return {'success': False, 'message': '图片保存失败，请检查格式是否为 JPG/PNG/WEBP'}

    # 保存 payment_qrcode 和 payment_type 到用户设置
    for key, value, desc in [
        ('payment_qrcode', image_url, '收款码图片路径'),
        ('payment_type', payment_type, '收款方式'),
    ]:
        stmt = select(UserSetting).where(
            UserSetting.user_id == current_user.id,
            UserSetting.key == key,
        )
        result = await session.execute(stmt)
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            session.add(UserSetting(user_id=current_user.id, key=key, value=value, description=desc))

    await session.commit()
    return {
        'success': True,
        'message': '收款码上传成功',
        'data': {'image_url': image_url, 'payment_type': payment_type},
    }
