"""统一通知渠道分发、历史渠道别名以及实际发送结果。

所有调用方共用发送入口，渠道返回失败时不再报告成功。
"""
from __future__ import annotations

from loguru import logger

from common.utils.notification_utils import (
    send_bark_notification,
    send_dingtalk_notification,
    send_email_notification,
    send_feishu_notification,
    send_pushplus_notification,
    send_telegram_notification,
    send_webhook_notification,
    send_wechat_notification,
)


async def dispatch_notification(
    channel_type: str,
    config: dict,
    message: str,
    attachment_path: str | None = None,
    **email_context,
) -> bool:
    """按渠道调用公共发送函数，返回实际结果。

    Args:
        channel_type: 渠道类型，支持历史别名。
        config: 已解析的渠道配置。
        message: 已渲染的通知内容。
        attachment_path: 邮件附件路径。
        email_context: 邮件日志所需的用户、操作与客户端IP信息。
    Returns:
        仅第三方发送函数确认成功时返回True；不支持的渠道抛出明确错误。
    """
    senders = {
        "ding_talk": send_dingtalk_notification,
        "dingtalk": send_dingtalk_notification,
        "feishu": send_feishu_notification,
        "lark": send_feishu_notification,
        "bark": send_bark_notification,
        "webhook": send_webhook_notification,
        "wechat": send_wechat_notification,
        "wechat_work": send_wechat_notification,
        "wecom": send_wechat_notification,
        "telegram": send_telegram_notification,
        "pushplus": send_pushplus_notification,
    }
    if channel_type == "email":
        success = await send_email_notification(config, message, attachment_path, **email_context)
    else:
        sender = senders.get(channel_type)
        if sender is None:
            raise ValueError(f"不支持的通知渠道类型：{channel_type}")
        success = await sender(config, message)
    if not success:
        logger.error("通知渠道发送失败：channel_type={}", channel_type)
    return bool(success)
