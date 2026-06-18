"""API 响应字段取值工具"""
from __future__ import annotations

import json
from typing import Any


RESPONSE_FIELD_EMPTY_MESSAGE = "响应字段取值失败为空"
_MISSING = object()


def extract_card_api_response_content(response_text: str, response_field: str | None = None) -> str:
    """从卡券 API 响应里提取发货内容，集中处理旧逻辑和新响应字段路径。"""
    normalized_field = (response_field or "").strip()
    if normalized_field:
        try:
            response_data = json.loads(response_text)
        except Exception:
            return RESPONSE_FIELD_EMPTY_MESSAGE

        value = get_response_field_value(response_data, normalized_field)
        return stringify_response_value(value)

    try:
        response_data = json.loads(response_text)
        if isinstance(response_data, dict):
            value = response_data.get("data") or response_data.get("content") or response_data.get("card") or response_data
            return stringify_response_value(value)
        return stringify_response_value(response_data)
    except Exception:
        return response_text


def get_response_field_value(data: Any, field_path: str) -> Any:
    """按类 lodash get 的路径读取响应值，支持 data.cards[0].key 这类常见写法。"""
    current = data
    tokens = parse_response_field_path(field_path)
    if not tokens:
        return _MISSING

    for token in tokens:
        if isinstance(token, int):
            if not isinstance(current, list) or token < 0 or token >= len(current):
                return _MISSING
            current = current[token]
            continue

        if not isinstance(current, dict) or token not in current:
            return _MISSING
        current = current[token]

    return current


def parse_response_field_path(field_path: str) -> list[str | int]:
    """把点号和数组下标路径拆成令牌，避免在业务代码里重复解析字符串。"""
    tokens: list[str | int] = []
    buffer = ""
    index = 0

    while index < len(field_path):
        char = field_path[index]
        if char == ".":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            index += 1
            continue

        if char == "[":
            if buffer:
                tokens.append(buffer)
                buffer = ""

            end_index = field_path.find("]", index)
            if end_index == -1:
                return []

            raw_index = field_path[index + 1:end_index].strip()
            if raw_index.isdigit():
                tokens.append(int(raw_index))
            else:
                tokens.append(raw_index.strip("\"'"))
            index = end_index + 1
            continue

        buffer += char
        index += 1

    if buffer:
        tokens.append(buffer)

    return tokens


def stringify_response_value(value: Any) -> str:
    """把取到的响应值转成最终发货文本，缺失或空字符串按约定返回提示。"""
    if value is _MISSING or value is None:
        return RESPONSE_FIELD_EMPTY_MESSAGE

    if isinstance(value, str):
        if not value.strip():
            return RESPONSE_FIELD_EMPTY_MESSAGE
        return value

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    if isinstance(value, bool):
        return json.dumps(value, ensure_ascii=False)

    return str(value)
