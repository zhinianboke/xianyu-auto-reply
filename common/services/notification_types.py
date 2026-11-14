"""
通知事件类型公共定义与校验。

功能：
1. 统一通知事件类型的字典类型和值顺序
2. 严格校验新写入的账号绑定级、渠道级通知类型
3. 兼容读取历史缺失或异常配置，避免升级后通知静默中断
"""
from __future__ import annotations

from collections.abc import Iterable


NOTIFICATION_TYPE_DICTIONARY = "notification_type"
DEFAULT_NOTIFICATION_TYPES = ("chat", "delivery", "account")


class NotificationTypeValueError(ValueError):
    """通知事件类型取值不合法。"""


def normalize_notification_types(value: object) -> tuple[str, ...]:
    """严格校验并按固定顺序返回通知事件类型。

    Args:
        value: 逗号分隔字符串或通知类型集合。
    Returns:
        去重并按固定顺序排列的通知类型元组。
    Raises:
        NotificationTypeValueError: 类型格式错误、为空或包含未知值。
    """
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, dict)):
        items = list(value)
    else:
        raise NotificationTypeValueError("通知类型格式错误，请重新选择")

    normalized = [str(item).strip() for item in items if str(item).strip()]
    if not normalized:
        raise NotificationTypeValueError("请至少选择一种通知类型")

    invalid = sorted(set(normalized).difference(DEFAULT_NOTIFICATION_TYPES))
    if invalid:
        raise NotificationTypeValueError(f"通知类型包含不支持的值：{', '.join(invalid)}")

    selected = set(normalized)
    return tuple(item for item in DEFAULT_NOTIFICATION_TYPES if item in selected)


def resolve_stored_notification_types(value: object) -> tuple[tuple[str, ...], bool]:
    """兼容解析数据库中的历史通知类型配置。

    Args:
        value: 数据库存储的通知类型值。
    Returns:
        二元组：可用通知类型、是否因异常值回退为全类型。
        历史缺失值属于正常兼容场景，不标记为异常回退。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return DEFAULT_NOTIFICATION_TYPES, False
    try:
        return normalize_notification_types(value), False
    except NotificationTypeValueError:
        return DEFAULT_NOTIFICATION_TYPES, True


__all__ = [
    "DEFAULT_NOTIFICATION_TYPES",
    "NOTIFICATION_TYPE_DICTIONARY",
    "NotificationTypeValueError",
    "normalize_notification_types",
    "resolve_stored_notification_types",
]
