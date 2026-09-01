"""通知正文模板的安全渲染工具。"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from loguru import logger


TEMPLATE_CONFIG_KEYS = {
    "chat": "chat_template",
    "delivery": "delivery_template",
    "account": "account_template",
}

TEMPLATE_VARIABLES = {
    "chat": {
        "account",
        "account_id",
        "account_remark",
        "buyer_nick",
        "buyer_id",
        "message",
        "item_id",
        "chat_id",
        "time",
    },
    "delivery": {
        "account",
        "account_id",
        "account_remark",
        "buyer_nick",
        "buyer_id",
        "message",
        "item_id",
        "chat_id",
        "time",
        "order_id",
        "amount",
        "quantity",
        "result",
    },
    "account": {
        "account",
        "account_id",
        "account_remark",
        "title",
        "notification_type",
        "detail",
        "chat_id",
        "verification_url",
        "verification_info",
        "time",
    },
}

_PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


def validate_notification_template(template: str, template_type: str) -> str | None:
    """校验通知模板；返回错误说明，合法时返回 ``None``。"""
    if template_type not in TEMPLATE_CONFIG_KEYS:
        return f"不支持的通知模板类型: {template_type}"
    if not isinstance(template, str):
        return "模板必须是文本"

    matches = list(_PLACEHOLDER_RE.finditer(template))
    remaining = _PLACEHOLDER_RE.sub("", template)
    if "{{" in remaining or "}}" in remaining:
        return "占位符必须使用 {{variable}} 格式"

    allowed_variables = TEMPLATE_VARIABLES[template_type]
    unknown_variables = sorted({match.group(1) for match in matches} - allowed_variables)
    if unknown_variables:
        return f"不支持的占位符: {', '.join(unknown_variables)}"
    return None


def render_notification_template(
    config_data: Mapping[str, Any] | None,
    template_type: str,
    context: Mapping[str, Any],
    default_message: str,
) -> str:
    """按渠道配置渲染模板；模板缺失或无效时回退系统默认正文。"""
    config_data = config_data or {}
    config_key = TEMPLATE_CONFIG_KEYS.get(template_type)
    template = config_data.get(config_key) if config_key else None

    if not isinstance(template, str) or not template.strip():
        return default_message

    validation_error = validate_notification_template(template, template_type)
    if validation_error:
        logger.warning("通知{}模板无效，已使用系统默认正文: {}", template_type, validation_error)
        return default_message

    def replace_placeholder(match: re.Match[str]) -> str:
        value = context.get(match.group(1))
        return "未知" if value is None else str(value)

    return _PLACEHOLDER_RE.sub(replace_placeholder, template)
