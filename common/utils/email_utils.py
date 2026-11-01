"""
邮箱地址校验工具。

功能：
1. 统一校验邮箱地址格式
2. 返回去除首尾空白并规范化后的邮箱地址
"""
from __future__ import annotations

from email_validator import EmailNotValidError, validate_email


def normalize_email_address(raw_value: str) -> tuple[str | None, str | None]:
    """
    校验并规范化邮箱地址。

    Args:
        raw_value: 待校验的邮箱地址。
    Returns:
        (规范化邮箱, 错误信息)，校验成功时错误信息为 None。
    """
    value = str(raw_value or "").strip()
    if not value:
        return None, "邮箱地址不能为空"
    try:
        result = validate_email(value, check_deliverability=False)
    except EmailNotValidError:
        return None, "邮箱地址格式不正确"
    return result.normalized, None
