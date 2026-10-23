"""
闲鱼官方账号识别工具。

功能：
1. 统一识别需要禁止回复的闲鱼官方机器人账号。
2. 检查完整消息报文是否包含被禁止的官方机器人接收方。
3. 提供发送前的接收方校验，统一返回明确的中文拒绝原因。
"""
from __future__ import annotations

from typing import Any

OFFICIAL_ROBOT_USER_IDS = frozenset({"2223046249624"})


def normalize_goofish_user_id(user_id: Any) -> str:
    """标准化闲鱼用户ID，移除空白和 ``@goofish`` 后缀。

    Args:
        user_id: 原始闲鱼用户ID。

    Returns:
        标准化后的用户ID；无有效值时返回空字符串。
    """
    return str(user_id or "").strip().split("@", 1)[0].strip()


def is_xianyu_official_robot_user(user_id: Any) -> bool:
    """判断用户ID是否属于需要禁止回复的闲鱼官方机器人。

    Args:
        user_id: 原始闲鱼用户ID。

    Returns:
        是官方机器人时返回True，否则返回False。
    """
    return normalize_goofish_user_id(user_id) in OFFICIAL_ROBOT_USER_IDS


def ensure_xianyu_message_recipient(user_id: Any) -> None:
    """校验消息接收方，禁止向闲鱼官方机器人发送消息。

    Args:
        user_id: 原始闲鱼用户 ID，允许携带 @goofish 后缀。
    Returns:
        校验通过时返回 None。
    Raises:
        ValueError: 接收方是禁止发送消息的官方机器人。
    """
    if is_xianyu_official_robot_user(user_id):
        raise ValueError("禁止向闲鱼官方机器人发送消息")


def message_targets_official_robot(message: Any) -> bool:
    """检查完整闲鱼发送报文是否以官方机器人作为接收方。

    Args:
        message: 待发送的完整LWP消息报文。

    Returns:
        接收方包含官方机器人时返回True，否则返回False。
    """
    if not isinstance(message, dict):
        return False

    body = message.get("body")
    if not isinstance(body, list):
        return False

    for body_item in body:
        if not isinstance(body_item, dict):
            continue
        receivers = body_item.get("actualReceivers")
        if not isinstance(receivers, (list, tuple, set)):
            continue
        if any(is_xianyu_official_robot_user(receiver) for receiver in receivers):
            return True
    return False
