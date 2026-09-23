"""
平台分类接口字段兼容工具。

功能：
1. 从平台不同版本的同义字段中读取文本值。
2. 解包字典、JSON 字符串、列表或嵌套结构的分类预测结果。
"""
from __future__ import annotations

import json
from typing import Any


def first_text(*values: Any) -> str:
    """从多个兼容字段中取第一个非空文本值。"""
    for value in values:
        text = str(value).strip() if value is not None else ""
        if text:
            return text
    return ""


def category_result(value: Any) -> dict[str, Any] | None:
    """兼容分类预测结果的字典、JSON 字符串、列表和嵌套结构。"""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if isinstance(value, list):
        value = next((item for item in value if isinstance(item, dict)), None)
    if not isinstance(value, dict):
        return None
    nested = value.get("data") or value.get("result")
    if isinstance(nested, (dict, list, str)):
        nested_result = category_result(nested)
        if nested_result:
            return nested_result
    return value


__all__ = ["category_result", "first_text"]
