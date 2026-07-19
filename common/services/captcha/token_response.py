"""
Token 接口滑块响应判断工具。

功能：
1. 统一判断 refresh_token 与定时 Token 续期的滑块触发场景
2. 提取 Token 响应中的 punish 验证链接
3. 返回命中的风控原因，便于调用方记录明确日志
"""
from __future__ import annotations

from typing import Any


TOKEN_CAPTCHA_KEYWORDS = (
    "FAIL_SYS_USER_VALIDATE",
    "RGV587_ERROR",
    "哎哟喂,被挤爆啦",
    "哎哟喂，被挤爆啦",
    "挤爆了",
    "请稍后重试",
    "punish?x5secdata",
    "captcha",
)


def extract_token_captcha_url(response_json: Any) -> str:
    """提取 Token 响应中的验证链接。"""
    if not isinstance(response_json, dict):
        return ""
    data = response_json.get("data")
    if not isinstance(data, dict):
        return ""
    return str(data.get("url") or "").strip()


def get_token_captcha_reason(response_json: Any) -> str | None:
    """返回 Token 响应需要滑块验证的原因，不需要时返回 ``None``。"""
    if not isinstance(response_json, dict):
        return None

    ret_value = response_json.get("ret", []) or []
    if isinstance(ret_value, str):
        ret_items = [ret_value]
    elif isinstance(ret_value, (list, tuple)):
        ret_items = ret_value
    else:
        ret_items = [ret_value]
    ret_text = " ".join(str(item) for item in ret_items)
    for keyword in TOKEN_CAPTCHA_KEYWORDS:
        if keyword in ret_text:
            return keyword

    verification_url = extract_token_captcha_url(response_json)
    if any(marker in verification_url for marker in ("punish", "captcha", "validate")):
        return "验证URL"
    return None


def is_token_captcha_required(response_json: Any) -> bool:
    """判断 Token 响应是否需要滑块验证。"""
    return get_token_captcha_reason(response_json) is not None
