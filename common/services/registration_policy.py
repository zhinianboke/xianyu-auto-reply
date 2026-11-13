"""
用户自助注册的公共准入规则。

功能：
1. 统一注册开关键名与拒绝提示
2. 为注册、注册验证码发送和验证提供相同的开关判断
"""
from __future__ import annotations

from collections.abc import Mapping

from common.services.system_setting_validation import parse_boolean_setting

REGISTRATION_ENABLED_KEY = "registration_enabled"
REGISTRATION_DISABLED_MESSAGE = "系统未开放注册，请联系管理员"


def get_registration_rejection_message(settings: Mapping[str, object]) -> str | None:
    """根据本次请求读取的有效设置判断是否允许自助注册。

    Args:
        settings: 当前系统设置；缺失注册开关时默认关闭。
    Returns:
        关闭时返回统一拒绝提示，开启时返回 None。
    """
    if parse_boolean_setting(settings.get(REGISTRATION_ENABLED_KEY)):
        return None
    return REGISTRATION_DISABLED_MESSAGE
