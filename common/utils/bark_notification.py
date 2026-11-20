"""Bark 聊天通知的默认标题、正文、分组和图标。"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from common.utils.notification_template import (
    BARK_CHAT_TITLE_TEMPLATE_KEY,
    render_bark_chat_title_template,
    validate_notification_template,
    validate_notification_templates,
)


DEFAULT_BARK_ICON_URL = (
    "https://is1-ssl.mzstatic.com/image/thumb/Purple221/v4/f5/01/e7/"
    "f501e794-30b4-c66c-2ec8-9730d5ebecf7/"
    "AppIcon-0-0-1x_U007epad-0-1-0-sRGB-85-220.png/512x512bb.jpg"
)


def prepare_bark_chat_notification(
    config_data: Mapping[str, Any],
    rendered_message: str,
    context: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    """为 Bark 聊天通知派生当次发送配置，不修改存储配置。"""
    config = dict(config_data)
    account_id = str(context.get("account_id") or "未知账号").strip()
    account_remark = str(
        context.get("_account_remark_raw", context.get("account_remark") or "")
    ).strip()
    buyer_nick = str(context.get("buyer_nick") or "未知").strip() or "未知"

    default_title = f"{account_remark or account_id}-{buyer_nick}"
    if BARK_CHAT_TITLE_TEMPLATE_KEY in config:
        title_template = config.get(BARK_CHAT_TITLE_TEMPLATE_KEY)
        if isinstance(title_template, str) and title_template.strip():
            validation_error = validate_notification_templates(
                {BARK_CHAT_TITLE_TEMPLATE_KEY: title_template}
            )
            config["title"] = (
                default_title
                if validation_error
                else render_bark_chat_title_template(
                    title_template,
                    {"account_remark": account_remark, "buyer_nick": buyer_nick},
                )
            )
        else:
            config["title"] = default_title
    else:
        # 聊天通知始终采用动态标题；历史通用 title 仍用于其他通知类型。
        config["title"] = default_title

    group_prefix = str(config.get("group") or account_remark or "闲鱼").strip() or "闲鱼"
    config["group"] = f"{group_prefix} · {account_id}"
    if not isinstance(config.get("icon"), str) or not config["icon"].strip():
        config["icon"] = DEFAULT_BARK_ICON_URL

    chat_template = config.get("chat_template")
    has_valid_custom_body = (
        isinstance(chat_template, str)
        and bool(chat_template.strip())
        and validate_notification_template(chat_template, "chat") is None
    )
    if has_valid_custom_body:
        body = rendered_message
    else:
        body = f"消息: {context.get('message') or ''}\n时间: {context.get('time') or ''}"
    return config, body
