"""渲染上新监控通知，复用公共渠道分发并记录邮件发送结果。"""
from __future__ import annotations

from typing import Any

from loguru import logger

from common.models.notification_channel import NotificationChannel
from common.services.email_log_service import EMAIL_OPERATION_MONITOR_NOTIFICATION, record_email_log
from common.services.notification_types import resolve_stored_notification_types
from common.utils.notification_config import parse_notification_config
from common.utils.notification_dispatch import dispatch_notification
from common.utils.notification_template import render_notification_template


async def send_channel_message(
    channel: NotificationChannel,
    message: str,
    *,
    owner_id: int | None = None,
) -> bool:
    """兼容旧调用方，并委托公共通知分发器发送。

    Args:
        channel: 待发送消息的通知渠道。
        message: 通知正文。
        owner_id: 触发发送的用户ID。
    Returns:
        渠道发送成功返回True，否则返回False。
    """
    channel_type = str(channel.channel_type or "").strip().lower()
    try:
        config = parse_notification_config(channel.config_payload)
        return await dispatch_notification(
            channel_type,
            config,
            message,
            owner_id=owner_id,
        )
    except Exception:
        logger.exception("通知渠道发送异常：channel_id={}, owner_id={}", channel.id, owner_id)
        return False


async def send_monitor_item_notification(
    channel: NotificationChannel,
    context: dict[str, Any],
    *,
    owner_id: int | None = None,
) -> bool:
    """按渠道级开关发送商品监控通知，邮件成功、失败及配置拒绝均记录日志。

    Args:
        channel: 任务所属用户的通知渠道。
        context: 商品与任务的模板变量。
        owner_id: 触发监控任务的用户ID。
    Returns:
        渠道确认发送成功时返回True，关闭或发送失败时返回False。
        调度任务没有客户端请求，邮件日志中的客户端IP保持空值。
    """
    channel_type = str(channel.channel_type or "").strip().lower()
    try:
        config = parse_notification_config(channel.config_payload)
    except ValueError as exc:
        logger.exception("上新通知渠道配置无效：channel_id={}, owner_id={}", channel.id, owner_id)
        if channel_type == "email":
            await record_email_log(
                recipient_email="",
                trigger_operation=EMAIL_OPERATION_MONITOR_NOTIFICATION,
                success=False,
                owner_id=owner_id,
                result_message=str(exc),
            )
        return False
    notify_types, fallback = resolve_stored_notification_types(config.get("notify_types"))
    if fallback:
        logger.warning(
            "渠道 {}({}) 的通知类型配置异常，已按全类型兼容",
            channel.name,
            channel.id,
        )
    if "monitor" not in notify_types:
        logger.info("渠道 {}({}) 已关闭上新监控通知", channel.name, channel.id)
        return False

    default_message = (
        "【闲鱼商品监控】\n"
        f"任务: {context.get('task_name', '未知')}\n\n"
        f"商品: {context.get('title', '未知')}\n"
        f"价格: {context.get('price', '未知')}\n"
        f"地区: {context.get('area', '未知')}\n"
        f"卖家: {context.get('seller_nick', '未知')}\n"
        f"卖家信用: {context.get('seller_credit', '未知')}\n"
        f"包邮: {context.get('free_shipping', '未知')}\n"
        f"标签: {context.get('tags', '未知')}\n"
        f"链接: {context.get('item_url', '')}\n"
        f"时间: {context.get('time', '')}"
    )
    message = render_notification_template(
        config, "monitor", context, default_message
    )
    try:
        return await dispatch_notification(
            channel_type,
            config,
            message,
            owner_id=owner_id,
            trigger_operation=EMAIL_OPERATION_MONITOR_NOTIFICATION,
        )
    except Exception as exc:
        logger.exception("上新通知发送异常：channel_id={}, owner_id={}", channel.id, owner_id)
        if channel_type == "email":
            await record_email_log(
                recipient_email=str(config.get("recipient_email") or ""),
                trigger_operation=EMAIL_OPERATION_MONITOR_NOTIFICATION,
                success=False,
                owner_id=owner_id,
                result_message=str(exc),
            )
        return False


__all__ = ["send_channel_message", "send_monitor_item_notification"]
