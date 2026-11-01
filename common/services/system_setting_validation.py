"""
系统设置通用字段校验。

功能：
1. 校验日志保留天数
2. 校验金额、端口、枚举和邮箱类系统设置
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from common.utils.email_utils import normalize_email_address


def parse_log_retention_days(raw_value: str) -> tuple[int | None, str | None]:
    """解析日志保留天数，范围为 1~365。"""
    value = str(raw_value or "").strip()
    if not value.isdigit():
        return None, "日志保留天数必须为1到365之间的整数"
    retention_days = int(value)
    if not 1 <= retention_days <= 365:
        return None, "日志保留天数必须为1到365之间的整数"
    return retention_days, None


def validate_decimal_setting(
    raw_value: str,
    *,
    field_name: str,
    allow_empty: bool = True,
    strictly_positive: bool = False,
) -> str | None:
    """校验金额或费率配置，最多保留两位小数。"""
    value = str(raw_value or "").strip()
    if not value:
        return None if allow_empty else f"{field_name}不能为空"
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        return f"{field_name}必须为有效数字，且最多保留两位小数"
    if not number.is_finite() or number.as_tuple().exponent < -2:
        return f"{field_name}必须为有效数字，且最多保留两位小数"
    if strictly_positive and number <= 0:
        return f"{field_name}必须大于0，且最多保留两位小数"
    if not strictly_positive and number < 0:
        return f"{field_name}不能小于0，且最多保留两位小数"
    return None


def validate_business_setting(key: str, raw_value: str) -> str | None:
    """校验通用接口可修改的数值、枚举与邮箱设置。"""
    value = str(raw_value or "").strip()
    if key == "smtp_port" and (not value.isdigit() or not 1 <= int(value) <= 65535):
        return "SMTP端口必须为1到65535之间的整数"
    if key == "smtp_user" and value:
        _, error_message = normalize_email_address(value)
        return "发件邮箱格式不正确" if error_message else None
    if key == "withdraw.notify_email" and value:
        _, error_message = normalize_email_address(value)
        return "提现通知邮箱格式不正确" if error_message else None
    if key == "withdraw.min_amount":
        return validate_decimal_setting(value, field_name="最低提现金额")
    if key == "distribution.fee_type" and value not in {"fixed", "percent"}:
        return "手续费类型无效，请选择固定金额或按订单金额百分比"
    if key == "distribution.fee_rate":
        return validate_decimal_setting(value, field_name="手续费")
    if key == "user.renew_month_price":
        return validate_decimal_setting(value, field_name="续期单价", strictly_positive=True)
    if key == "user.register_default_days" and value and (not value.isdigit() or int(value) <= 0):
        return "注册默认天数必须为正整数，留空表示不设置到期日"
    return None
