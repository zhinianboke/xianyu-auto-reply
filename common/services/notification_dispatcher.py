"""复用系统通知渠道发送任意业务通知。"""
from __future__ import annotations

from typing import Any

from loguru import logger

from common.models.notification_channel import NotificationChannel
from common.utils.notification_template import (
    is_notification_event_enabled,
    render_notification_template,
)
from common.utils.notification_utils import (
    parse_notification_config,
    send_bark_notification,
    send_dingtalk_notification,
    send_email_notification,
    send_feishu_notification,
    send_pushplus_notification,
    send_telegram_notification,
    send_webhook_notification,
    send_wechat_notification,
)


async def send_channel_message(
    channel: NotificationChannel,
    message: str,
    *,
    owner_id: int | None = None,
) -> bool:
    """按渠道类型发送消息，并以布尔值返回真实发送结果。"""
    config = parse_notification_config(channel.config_payload or {})
    channel_type = str(channel.channel_type or "").strip().lower()
    try:
        if channel_type in {"ding_talk", "dingtalk"}:
            return await send_dingtalk_notification(config, message)
        if channel_type in {"feishu", "lark"}:
            return await send_feishu_notification(config, message)
        if channel_type == "bark":
            return await send_bark_notification(config, message)
        if channel_type == "email":
            return await send_email_notification(config, message, owner_id=owner_id)
        if channel_type == "webhook":
            return await send_webhook_notification(config, message)
        if channel_type in {"wechat", "wechat_work"}:
            return await send_wechat_notification(config, message)
        if channel_type == "telegram":
            return await send_telegram_notification(config, message)
        if channel_type == "pushplus":
            return await send_pushplus_notification(config, message)
        logger.warning("不支持的通知渠道类型: {}", channel.channel_type)
    except Exception as exc:  # noqa: BLE001
        logger.error("发送通知渠道 {}({}) 异常: {}", channel.name, channel.id, exc)
    return False


async def send_monitor_item_notification(
    channel: NotificationChannel,
    context: dict[str, Any],
    *,
    owner_id: int | None = None,
) -> bool:
    """渲染商品监控模板并发送。"""
    config = channel.config_payload or {}
    if not is_notification_event_enabled(config, "monitor"):
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
    return await send_channel_message(channel, message, owner_id=owner_id)


__all__ = ["send_channel_message", "send_monitor_item_notification"]
