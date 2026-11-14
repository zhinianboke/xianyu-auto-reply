"""兼容读取历史通知配置，统一对象、JSON字符串和旧版地址字符串。"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit


def parse_notification_config(config: object) -> dict[str, Any]:
    """将渠道配置解析为对象；保留旧版纯地址，拒绝非对象JSON。

    Args:
        config: 数据库存储的对象、JSON字符串或历史纯地址字符串。
    Returns:
        渠道配置对象；缺省配置返回空对象。
    Raises:
        ValueError: 配置为数组、数字等无法作为渠道配置使用的值。
    """
    if config is None:
        return {}
    if isinstance(config, dict):
        return dict(config)
    if isinstance(config, str):
        if not config.strip():
            return {}
        try:
            parsed = json.loads(config)
        except json.JSONDecodeError:
            # 老版本钉钉渠道允许直接保存Webhook地址。
            parsed = config
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str):
            address = parsed.strip()
            try:
                url = urlsplit(address)
                if (
                    url.scheme.lower() in ("http", "https") and url.hostname
                    and not any(character.isspace() or ord(character) < 32 for character in address)
                ):
                    return {"config": address}
            except ValueError as error:
                raise ValueError("历史通知地址格式错误，请在通知渠道页面修复") from error
    raise ValueError("通知渠道配置必须为JSON对象，请在通知渠道页面修复")
