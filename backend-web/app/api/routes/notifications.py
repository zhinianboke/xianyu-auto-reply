from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.api import deps
from common.models.user import User
from common.schemas.common import ApiResponse
from common.schemas.notification import (
    MessageNotificationSet,
    NotificationChannelCreate,
    NotificationChannelUpdate,
)
from app.services.notification_service import (
    MessageNotificationService,
    NotificationChannelService,
)

channels_router = APIRouter(prefix="/notification-channels", tags=["notifications"])
messages_router = APIRouter(prefix="/message-notifications", tags=["notifications"])


@channels_router.get("")
async def list_notification_channels(
    current_user: User = Depends(deps.get_current_active_user),
    service: NotificationChannelService = Depends(deps.get_notification_channel_service),
) -> list[dict]:
    return await service.list_channels(current_user.id)


@channels_router.post("", response_model=ApiResponse)
async def create_notification_channel(
    payload: NotificationChannelCreate,
    current_user: User = Depends(deps.get_current_active_user),
    service: NotificationChannelService = Depends(deps.get_notification_channel_service),
) -> ApiResponse:
    await service.create_channel(current_user.id, payload)
    return ApiResponse(success=True, message="通知渠道已创建")


@channels_router.put("/{channel_id}", response_model=ApiResponse)
async def update_notification_channel(
    channel_id: int,
    payload: NotificationChannelUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    service: NotificationChannelService = Depends(deps.get_notification_channel_service),
) -> ApiResponse:
    updated = await service.update_channel(current_user.id, channel_id, payload)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知渠道不存在")
    return ApiResponse(success=True, message="通知渠道已更新")


@channels_router.delete("/{channel_id}", response_model=ApiResponse)
async def delete_notification_channel(
    channel_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    service: NotificationChannelService = Depends(deps.get_notification_channel_service),
) -> ApiResponse:
    deleted = await service.delete_channel(current_user.id, channel_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知渠道不存在")
    return ApiResponse(success=True, message="通知渠道已删除")


@channels_router.post("/{channel_id}/test", response_model=ApiResponse)
async def test_notification_channel(
    channel_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    service: NotificationChannelService = Depends(deps.get_notification_channel_service),
) -> ApiResponse:
    """测试通知渠道"""
    import time
    from loguru import logger
    from common.utils.notification_utils import (
        parse_notification_config,
        send_dingtalk_notification,
        send_feishu_notification,
        send_bark_notification,
        send_email_notification,
        send_webhook_notification,
        send_wechat_notification,
        send_telegram_notification,
        send_pushplus_notification
    )
    
    # 获取渠道信息
    channel = await service.get_channel(current_user.id, channel_id)
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知渠道不存在")
    
    channel_type = channel.channel_type
    channel_config = channel.config_payload
    
    # 构造测试消息
    test_message = f"🔔 通知渠道测试\n\n" \
                   f"渠道名称: {channel.name}\n" \
                   f"渠道类型: {channel_type}\n" \
                   f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
                   f"如果您收到此消息，说明通知渠道配置正确！"
    
    try:
        config_data = parse_notification_config(channel_config)
        logger.info(f"📱 测试通知渠道: {channel_type}, 配置: {config_data}")
        
        if channel_type in ('ding_talk', 'dingtalk'):
            await send_dingtalk_notification(config_data, test_message)
        elif channel_type in ('feishu', 'lark'):
            await send_feishu_notification(config_data, test_message)
        elif channel_type == 'bark':
            await send_bark_notification(config_data, test_message)
        elif channel_type == 'email':
            await send_email_notification(config_data, test_message)
        elif channel_type == 'webhook':
            await send_webhook_notification(config_data, test_message)
        elif channel_type == 'wechat':
            await send_wechat_notification(config_data, test_message)
        elif channel_type == 'telegram':
            await send_telegram_notification(config_data, test_message)
        elif channel_type == 'pushplus':
            await send_pushplus_notification(config_data, test_message)
        else:
            return ApiResponse(success=False, message=f"不支持的通知渠道类型: {channel_type}")
        
        logger.info(f"📱 测试通知发送成功: {channel.name}")
        return ApiResponse(success=True, message="测试消息发送成功")
        
    except Exception as e:
        logger.error(f"📱 测试通知发送失败: {str(e)}")
        return ApiResponse(success=False, message=f"发送失败: {str(e)}")


@messages_router.get("")
async def list_message_notifications(
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> dict:
    return await service.list_notifications(current_user.id)


@messages_router.get("/{cookie_id}")
async def list_message_notifications_for_account(
    cookie_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> list[dict]:
    return await service.list_for_account(current_user.id, cookie_id)


@messages_router.post("/{cookie_id}", response_model=ApiResponse)
async def set_message_notification(
    cookie_id: str,
    payload: MessageNotificationSet,
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> ApiResponse:
    success = await service.set_notification(current_user.id, cookie_id, payload)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号或通知渠道不存在")
    return ApiResponse(success=True, message="消息通知配置已更新")


@messages_router.delete("/{notification_id}", response_model=ApiResponse)
async def delete_message_notification(
    notification_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> ApiResponse:
    deleted = await service.delete_subscription(current_user.id, notification_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息通知不存在")
    return ApiResponse(success=True, message="消息通知已删除")


@messages_router.delete("/account/{cookie_id}", response_model=ApiResponse)
async def delete_account_notifications(
    cookie_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> ApiResponse:
    deleted = await service.delete_for_account(current_user.id, cookie_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在或没有通知配置")
    return ApiResponse(success=True, message="账号通知配置已清理")
