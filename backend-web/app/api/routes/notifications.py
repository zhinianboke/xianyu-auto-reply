from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from loguru import logger

from app.api import deps
from common.models.user import User
from common.schemas.common import ApiResponse
from common.services.email_log_service import EMAIL_OPERATION_NOTIFICATION_CHANNEL_TEST, record_email_log
from common.utils.http_utils import get_client_ip
from common.utils.time_utils import get_beijing_now_naive
from common.utils.notification_utils import parse_notification_config
from common.utils.notification_dispatch import dispatch_notification
from common.schemas.notification import (
    MessageNotificationSet,
    MessageNotificationToggle,
    NotificationChannelCreate,
    NotificationChannelUpdate,
)
from app.services.notification_service import (
    MessageNotificationService,
    NotificationChannelService,
    NotificationConfigValidationError,
    NotificationTemplateValidationError,
    NotificationTypeValidationError,
)

channels_router = APIRouter(prefix="/notification-channels", tags=["notifications"])
messages_router = APIRouter(prefix="/message-notifications", tags=["notifications"])


@channels_router.get("")
async def list_notification_channels(
    current_user: User = Depends(deps.get_current_active_user),
    service: NotificationChannelService = Depends(deps.get_notification_channel_service),
) -> list[dict]:
    return await service.list_channels(current_user.id)


@channels_router.get("/page", response_model=ApiResponse)
async def list_notification_channel_page(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(deps.get_current_active_user),
    service: NotificationChannelService = Depends(deps.get_notification_channel_service),
) -> ApiResponse:
    """分页读取通知渠道，保留原数组接口供账号选择和旧客户端使用。"""
    data = await service.list_channel_page(current_user.id, page, page_size)
    return ApiResponse(success=True, message="操作成功", data=data)


@channels_router.post("", response_model=ApiResponse)
async def create_notification_channel(
    payload: NotificationChannelCreate,
    current_user: User = Depends(deps.get_current_active_user),
    service: NotificationChannelService = Depends(deps.get_notification_channel_service),
) -> ApiResponse:
    try:
        await service.create_channel(current_user.id, payload)
    except (NotificationConfigValidationError, NotificationTemplateValidationError, NotificationTypeValidationError) as error:
        return ApiResponse(success=False, code=40001, message=str(error), data=None)
    return ApiResponse(success=True, message="通知渠道已创建")


@channels_router.put("/{channel_id}", response_model=ApiResponse)
async def update_notification_channel(
    channel_id: int,
    payload: NotificationChannelUpdate,
    current_user: User = Depends(deps.get_current_active_user),
    service: NotificationChannelService = Depends(deps.get_notification_channel_service),
) -> ApiResponse:
    try:
        updated = await service.update_channel(current_user.id, channel_id, payload)
    except (NotificationConfigValidationError, NotificationTemplateValidationError, NotificationTypeValidationError) as error:
        return ApiResponse(success=False, code=40001, message=str(error), data=None)
    if not updated:
        return ApiResponse(success=False, code=40401, message="通知渠道不存在", data=None)
    return ApiResponse(success=True, message="通知渠道已更新")


@channels_router.delete("/{channel_id}", response_model=ApiResponse)
async def delete_notification_channel(
    channel_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    service: NotificationChannelService = Depends(deps.get_notification_channel_service),
) -> ApiResponse:
    deleted = await service.delete_channel(current_user.id, channel_id)
    if not deleted:
        return ApiResponse(success=False, code=40401, message="通知渠道不存在", data=None)
    return ApiResponse(success=True, message="通知渠道已删除")


@channels_router.post("/{channel_id}/test", response_model=ApiResponse)
async def test_notification_channel(
    channel_id: int,
    http_request: Request,
    current_user: User = Depends(deps.get_current_active_user),
    service: NotificationChannelService = Depends(deps.get_notification_channel_service),
) -> ApiResponse:
    """测试通知渠道"""
    # 获取渠道信息
    channel = await service.get_channel(current_user.id, channel_id)
    if not channel:
        return ApiResponse(success=False, code=40401, message="通知渠道不存在", data=None)
    
    channel_type = channel.channel_type
    channel_config = channel.config_payload
    
    # 构造测试消息
    test_message = f"🔔 通知渠道测试\n\n" \
                   f"渠道名称: {channel.name}\n" \
                   f"渠道类型: {channel_type}\n" \
                   f"测试时间: {get_beijing_now_naive().strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
                   f"如果您收到此消息，说明通知渠道配置正确！"
    
    try:
        try:
            config_data = parse_notification_config(channel_config)
        except ValueError as error:
            # 解析失败发生在发送入口之前，邮件测试仍需记录此次被拒绝的尝试。
            if channel_type == "email":
                await record_email_log(
                    recipient_email="",
                    trigger_operation=EMAIL_OPERATION_NOTIFICATION_CHANNEL_TEST,
                    success=False,
                    owner_id=current_user.id,
                    client_ip=get_client_ip(http_request),
                    result_message=f"邮件通知渠道配置解析失败: {error}",
                )
            raise
        logger.info(f"📱 测试通知渠道: {channel_type}, 配置: {config_data}")
        
        ok = await dispatch_notification(
            channel_type, config_data, test_message,
            owner_id=current_user.id,
            trigger_operation=EMAIL_OPERATION_NOTIFICATION_CHANNEL_TEST,
            client_ip=get_client_ip(http_request),
        )
        if not ok:
            return ApiResponse(
                success=False, code=40001,
                message="通知发送失败，请检查渠道配置及服务端发送日志", data=None,
            )

        logger.info(f"📱 测试通知发送成功: {channel.name}")
        return ApiResponse(success=True, message="测试消息发送成功")
        
    except Exception as e:
        logger.exception(f"📱 测试通知发送失败: {str(e)}")
        return ApiResponse(success=False, code=40001, message=f"发送失败: {str(e)}", data=None)


@messages_router.get("")
async def list_message_notifications(
    page: int | None = Query(None, ge=1, description="兼容移动端的可选页码"),
    page_size: int | None = Query(None, ge=1, le=500, description="兼容移动端的可选每页数量"),
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> dict | list[dict]:
    # 旧网页不传分页参数，继续返回按账号分组的历史结构；
    # 已有移动端会传 page/page_size 并按数组解析，此时返回扁平列表兼容其既有调用。
    if page is not None or page_size is not None:
        data = await service.list_notification_page(
            current_user.id,
            page or 1,
            page_size or 20,
        )
        return [
            {**item, "enabled": item["subscription_enabled"]}
            for item in data["items"]
        ]
    return await service.list_notifications(current_user.id)


@messages_router.get("/options", response_model=ApiResponse)
async def get_message_notification_options(
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> ApiResponse:
    """读取通知事件类型数据字典，供网页统一展示中文名称。"""
    _ = current_user
    options = await service.get_notify_type_options()
    return ApiResponse(success=True, message="操作成功", data={"notify_types": options})


@messages_router.get("/page", response_model=ApiResponse)
async def list_message_notification_page(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> ApiResponse:
    """分页读取当前用户的消息通知绑定。"""
    data = await service.list_notification_page(current_user.id, page, page_size)
    return ApiResponse(success=True, message="操作成功", data=data)


@messages_router.get("/account/{cookie_id}")
async def list_message_notifications_for_account(
    cookie_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> list[dict]:
    return await service.list_for_account(current_user.id, cookie_id)


@messages_router.delete("/account/{cookie_id}", response_model=ApiResponse)
async def delete_account_notifications(
    cookie_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> ApiResponse:
    deleted = await service.delete_for_account(current_user.id, cookie_id)
    if not deleted:
        return ApiResponse(success=False, code=40401, message="账号不存在或没有通知配置", data=None)
    return ApiResponse(success=True, message="账号通知配置已清理")


@messages_router.post("/account/{cookie_id}", response_model=ApiResponse)
async def set_message_notification(
    cookie_id: str,
    payload: MessageNotificationSet,
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> ApiResponse:
    try:
        success = await service.set_notification(current_user.id, cookie_id, payload)
    except NotificationTypeValidationError as error:
        return ApiResponse(success=False, code=40001, message=str(error), data=None)
    if not success:
        return ApiResponse(success=False, code=40401, message="账号或通知渠道不存在", data=None)
    return ApiResponse(success=True, message="消息通知配置已更新")


@messages_router.delete("/{notification_id}", response_model=ApiResponse)
async def delete_message_notification(
    notification_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> ApiResponse:
    deleted = await service.delete_subscription(current_user.id, notification_id)
    if not deleted:
        return ApiResponse(success=False, code=40401, message="消息通知不存在", data=None)
    return ApiResponse(success=True, message="消息通知已删除")


@messages_router.put("/{notification_id}", response_model=ApiResponse)
async def update_message_notification_enabled(
    notification_id: int,
    payload: MessageNotificationToggle,
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> ApiResponse:
    """按绑定ID更新启停状态，兼容已有移动端接口。"""
    updated = await service.update_subscription_enabled(
        current_user.id,
        notification_id,
        payload.enabled,
    )
    if not updated:
        return ApiResponse(success=False, code=40401, message="消息通知不存在", data=None)
    return ApiResponse(success=True, message="消息通知状态已更新")


@messages_router.get("/{cookie_id}", include_in_schema=False)
async def list_message_notifications_for_account_compat(
    cookie_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> list[dict]:
    """兼容旧客户端的按账号查询路径。"""
    return await service.list_for_account(current_user.id, cookie_id)


@messages_router.post("/{cookie_id}", response_model=ApiResponse, include_in_schema=False)
async def set_message_notification_compat(
    cookie_id: str,
    payload: MessageNotificationSet,
    current_user: User = Depends(deps.get_current_active_user),
    service: MessageNotificationService = Depends(deps.get_message_notification_service),
) -> ApiResponse:
    """兼容旧客户端的按账号保存路径。"""
    return await set_message_notification(cookie_id, payload, current_user, service)
