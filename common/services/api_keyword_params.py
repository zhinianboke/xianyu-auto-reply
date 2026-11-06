"""API关键词参数处理：提取消息链接，并兼容历史actId消息占位符。"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from common.services.delivery_utils import recursive_replace_params

_MESSAGE_URL = re.compile(r"https?://[^\s<>\"'`￥，。！？；：、【】「」『』（）]+", re.IGNORECASE)


def extract_first_message_url(message: str) -> str:
    """返回消息中第一个有效HTTP/HTTPS链接；忽略外围标点，无链接返回空串。"""
    for match in _MESSAGE_URL.finditer(message):
        candidate = match.group().rstrip(".,!;:")
        # 分享文案常用括号包裹链接；只移除不属于链接的末尾闭括号。
        brackets = {")": "(", "]": "[", "}": "{"}
        while candidate and candidate[-1] in brackets:
            closing = candidate[-1]
            if candidate.count(closing) <= candidate.count(brackets[closing]):
                break
            candidate = candidate[:-1].rstrip(".,!;:")
        try:
            parsed = urlsplit(candidate)
            if parsed.hostname and parsed.port != 0:
                return candidate
        except ValueError:
            continue
    return ""


def _normalize_legacy_act_id(value: Any) -> Any:
    """复制参数模板，将actId键下的历史{message}转换为{actId}，保持其他值。"""
    if isinstance(value, dict):
        return {
            key: "{actId}" if key == "actId" and item == "{message}" else _normalize_legacy_act_id(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_legacy_act_id(item) for item in value]
    return value


def build_api_keyword_params(params: dict[str, Any], item_id: str, message: str) -> dict[str, Any]:
    """构造真实请求参数：actId优先取首个链接，否则用完整消息，message始终用原消息。

    Args:
        params: 已保存的JSON参数模板，支持新占位符及历史actId配置。
        item_id: 当前商品ID。
        message: 买家发送的完整消息。
    Returns:
        替换后的参数副本，不修改数据库配置或已处理中消息的快照。
    """
    return recursive_replace_params(
        _normalize_legacy_act_id(params),
        {"item_id": item_id or "", "message": message, "actId": extract_first_message_url(message) or message},
        single_pass=True,
    )
