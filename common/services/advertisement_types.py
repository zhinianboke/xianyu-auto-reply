"""广告类型定义、展示位置及费用设置键，前后端中文名称由数据字典统一提供。"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from common.models.advertisement import AdType

AD_TYPE_DICTIONARY = "advertisement_type"
AD_TYPE_LABELS = {
    AdType.CAROUSEL: "仪表盘轮播图",
    AdType.TEXT: "仪表盘文字广告",
    AdType.HOME_CAROUSEL: "首页轮播图",
    AdType.HOME_TEXT: "首页文字广告",
}
AD_PRICE_DEFAULTS = {
    f"ad_price.{ad_type.value}": ("", f"{label if label.endswith('广告') else label + '广告'}每月费用（元），空=未配置")
    for ad_type, label in AD_TYPE_LABELS.items()
}
AD_PLACEMENT_TYPES = {
    "dashboard": (AdType.CAROUSEL, AdType.TEXT),
    "home": (AdType.HOME_CAROUSEL, AdType.HOME_TEXT),
}


def get_placement_types(placement: str) -> tuple[AdType, AdType]:
    """返回指定展示位置的轮播与文字类型，非法位置直接报错。"""
    if placement not in AD_PLACEMENT_TYPES:
        raise ValueError("广告展示位置无效")
    return AD_PLACEMENT_TYPES[placement]


def parse_ad_price(value: str | None) -> Decimal | None:
    """校验单月费用，空值表示未配置；非空值必须为正数且最多两位小数。"""
    if not value or not value.strip():
        return None
    try:
        price = Decimal(value)
        if not price.is_finite() or price <= 0 or price != price.quantize(Decimal('0.01')):
            raise ValueError('无效金额')
        return price
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('广告每月费用必须大于0，且最多保留两位小数；留空表示未配置') from exc
