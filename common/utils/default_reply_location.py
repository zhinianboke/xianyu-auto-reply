"""Validation helpers for location-based external contact replies."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

EXTERNAL_CONTACT_REPLY_TYPE = "external_contact"


def validate_external_contact_fields(
    *,
    remote_url: str,
    location_name: str,
    longitude: str,
    latitude: str,
    title: str,
    subtitle: str = "",
) -> str | None:
    """Return a user-facing validation error, or ``None`` when valid."""
    if not remote_url.strip():
        return "请先到个人设置的远程URL配置中填写位置聊天远程URL"
    if not location_name.strip():
        return "请选择定位信息"
    if len(location_name.strip()) > 255:
        return "定位名称不能超过255个字符"
    if not title.strip():
        return "请输入位置标题"
    if len(title.strip()) > 128:
        return "位置标题不能超过128个字符"
    if len(subtitle.strip()) > 255:
        return "位置副标题不能超过255个字符"

    try:
        longitude_value = Decimal(longitude.strip())
        latitude_value = Decimal(latitude.strip())
    except (InvalidOperation, AttributeError):
        return "定位信息缺少有效经纬度，请重新选择地址"
    if not longitude_value.is_finite() or not latitude_value.is_finite():
        return "定位信息经纬度无效，请重新选择地址"
    if not Decimal("-180") <= longitude_value <= Decimal("180"):
        return "经度必须在-180至180之间"
    if not Decimal("-90") <= latitude_value <= Decimal("90"):
        return "纬度必须在-90至90之间"
    return None


__all__ = ["EXTERNAL_CONTACT_REPLY_TYPE", "validate_external_contact_fields"]
