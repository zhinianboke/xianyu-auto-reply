"""
系统设置保存前的统一校验与规范化服务。

功能：
1. 对单项和批量系统设置执行相同校验
2. 基于批量提交后的完整目标状态校验跨字段约束
3. 规范化枚举、数字、邮箱和远程接口配置
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.services.system_setting_service import SENSITIVE_KEYS, SystemSettingService
from common.services.advertisement_types import AD_PRICE_DEFAULTS, parse_ad_price
from common.services.remote_password_login_api import (
    validate_remote_password_login_settings,
)
from common.services.remote_token_api import (
    TOKEN_REMOTE_SECRET_KEY_SETTING_KEY,
    TOKEN_REMOTE_URL_SETTING_KEY,
    validate_remote_token_settings,
)
from common.services.system_setting_validation import (
    parse_log_retention_days,
    validate_business_setting,
)
from common.services.token_api_mode import (
    TOKEN_API_MODE_REMOTE,
    TOKEN_API_MODE_SETTING_KEY,
    TOKEN_API_MODES,
)
from common.utils.email_utils import normalize_email_address

LOG_RETENTION_KEY = "log.retention_days"
PASSWORD_LOGIN_MODE_KEY = "password_login.mode"
PASSWORD_LOGIN_MODES = {"protocol", "browser"}
PASSWORD_LOGIN_PROTOCOL_MODE = "protocol"
PASSWORD_LOGIN_REMOTE_URL_KEY = "password_login.remote_url"
PASSWORD_LOGIN_REMOTE_SECRET_KEY_KEY = "password_login.remote_secret_key"
CAPTCHA_SLIDER_MODE_KEY = "captcha.slider_mode"
CAPTCHA_SLIDER_MODES = {"browser", "real_mouse"}
PROXY_URL_KEY = "proxy.api_url"
PROXY_ENABLED_KEY = "proxy.enabled"

_TRUE_VALUES = {"true", "1", "yes", "on"}
_TRIMMED_SETTING_KEYS = {
    "smtp_port",
    "smtp_user",
    "withdraw.notify_email",
    "withdraw.min_amount",
    "distribution.fee_type",
    "distribution.fee_rate",
    "user.renew_month_price",
    "user.register_default_days",
    LOG_RETENTION_KEY,
    PASSWORD_LOGIN_REMOTE_URL_KEY,
    PASSWORD_LOGIN_REMOTE_SECRET_KEY_KEY,
    TOKEN_REMOTE_URL_SETTING_KEY,
    TOKEN_REMOTE_SECRET_KEY_SETTING_KEY,
    PROXY_URL_KEY,
}


@dataclass(frozen=True, slots=True)
class ValidatedSystemSettings:
    """校验成功后的设置值及需要实时刷新的日志保留天数。"""

    values: dict[str, str]
    retention_days: int | None = None


def _is_truthy(raw_value: object) -> bool:
    """统一解析系统设置中的布尔字符串。"""
    return str(raw_value or "").strip().lower() in _TRUE_VALUES


def _normalize_email_setting(key: str, value: str) -> tuple[str, str | None]:
    """规范化允许留空的邮箱设置。"""
    if key not in {"smtp_user", "withdraw.notify_email"} or not value:
        return value, None
    normalized, error_message = normalize_email_address(value)
    if error_message:
        field_name = "发件邮箱" if key == "smtp_user" else "提现通知邮箱"
        return value, f"{field_name}格式不正确"
    return normalized or "", None


def _normalize_setting_value(key: str, raw_value: str) -> tuple[str, str | None]:
    """规范化并校验单个设置值，不处理需要完整目标状态的跨字段约束。"""
    value = str(raw_value or "")
    if key in _TRIMMED_SETTING_KEYS:
        value = value.strip()

    if key in AD_PRICE_DEFAULTS:
        try:
            parse_ad_price(value)
        except ValueError as exc:
            return value, str(exc)

    if key == PASSWORD_LOGIN_MODE_KEY:
        value = value.strip().lower()
        if value == "auto":
            value = "browser"
        if value not in PASSWORD_LOGIN_MODES:
            return value, "账号密码登录方式无效，请选择协议登录或浏览器登录"

    if key == CAPTCHA_SLIDER_MODE_KEY:
        value = value.strip().lower()
        if value not in CAPTCHA_SLIDER_MODES:
            return value, "滑块滑动方式无效，请选择浏览器自动滑动或真实鼠标滑动"

    if key == TOKEN_API_MODE_SETTING_KEY:
        value = value.strip().lower()
        if value not in TOKEN_API_MODES:
            return value, "Token获取方式无效，请选择网页接口或远程接口"

    if key == LOG_RETENTION_KEY:
        _, error_message = parse_log_retention_days(value)
        if error_message:
            return value, error_message

    value, email_error = _normalize_email_setting(key, value)
    if email_error:
        return value, email_error

    business_error = validate_business_setting(key, value)
    return value, business_error


def _validate_target_state(target: Mapping[str, str], changed_keys: set[str]) -> str | None:
    """基于本次提交后的完整目标状态校验跨字段约束。"""
    if changed_keys.intersection({PROXY_URL_KEY, PROXY_ENABLED_KEY}):
        proxy_url = str(target.get(PROXY_URL_KEY) or "").strip()
        if _is_truthy(target.get(PROXY_ENABLED_KEY)) and not proxy_url:
            return "开启代理前请先填写代理 API 的 URL"

    token_keys = {
        TOKEN_API_MODE_SETTING_KEY,
        TOKEN_REMOTE_URL_SETTING_KEY,
        TOKEN_REMOTE_SECRET_KEY_SETTING_KEY,
    }
    if changed_keys.intersection(token_keys):
        token_mode = str(target.get(TOKEN_API_MODE_SETTING_KEY) or "").strip().lower()
        if token_mode == TOKEN_API_MODE_REMOTE:
            error_message = validate_remote_token_settings(
                str(target.get(TOKEN_REMOTE_URL_SETTING_KEY) or ""),
                str(target.get(TOKEN_REMOTE_SECRET_KEY_SETTING_KEY) or ""),
            )
            if error_message:
                return error_message

    password_login_keys = {
        PASSWORD_LOGIN_MODE_KEY,
        PASSWORD_LOGIN_REMOTE_URL_KEY,
        PASSWORD_LOGIN_REMOTE_SECRET_KEY_KEY,
    }
    if changed_keys.intersection(password_login_keys):
        login_mode = str(target.get(PASSWORD_LOGIN_MODE_KEY) or "").strip().lower()
        if login_mode == PASSWORD_LOGIN_PROTOCOL_MODE:
            error_message = validate_remote_password_login_settings(
                str(target.get(PASSWORD_LOGIN_REMOTE_URL_KEY) or ""),
                str(target.get(PASSWORD_LOGIN_REMOTE_SECRET_KEY_KEY) or ""),
            )
            if error_message:
                return error_message
    return None


async def validate_system_settings_update(
    updates: Mapping[str, str],
    service: SystemSettingService,
) -> tuple[ValidatedSystemSettings | None, str | None]:
    """
    校验并规范化一组系统设置。

    Args:
        updates: 本次需要保存的设置键值。
        service: 系统设置服务，用于读取当前状态完成跨字段校验。
    Returns:
        (校验结果, 错误信息)，校验失败时结果为 None。
    """
    if not updates:
        return None, "没有需要保存的系统设置"

    sensitive_keys = set(updates).intersection(SENSITIVE_KEYS)
    if sensitive_keys:
        return None, "该设置需要使用专用接口修改"

    normalized: dict[str, str] = {}
    for key, raw_value in updates.items():
        value, error_message = _normalize_setting_value(key, raw_value)
        if error_message:
            return None, error_message
        normalized[key] = value

    current_settings = await service.list_settings()
    target_settings = {**current_settings, **normalized}
    target_error = _validate_target_state(target_settings, set(normalized))
    if target_error:
        return None, target_error

    retention_days = None
    if LOG_RETENTION_KEY in normalized:
        retention_days, _ = parse_log_retention_days(normalized[LOG_RETENTION_KEY])
    return ValidatedSystemSettings(normalized, retention_days), None
