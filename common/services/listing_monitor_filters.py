"""商品监控筛选与详情字段解析。"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


CREDIT_LABELS = {
    1: "信用较差",
    2: "信用中等",
    3: "信用良好",
    4: "信用优秀",
    5: "信用极好",
}


def normalize_keywords(values: Iterable[Any] | None) -> list[str]:
    """清理关键词列表并去重，保留用户输入顺序。"""
    result: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def matches_text_filters(item: dict[str, Any], include: Iterable[str], exclude: Iterable[str]) -> bool:
    """只按商品标题筛选；包含词为 AND，排除词为 OR，不区分英文大小写。"""
    haystack = str(item.get("title") or "").casefold()
    include_words = [word.casefold() for word in normalize_keywords(include)]
    exclude_words = [word.casefold() for word in normalize_keywords(exclude)]
    return all(word in haystack for word in include_words) and not any(
        word in haystack for word in exclude_words
    )


def extract_free_shipping(detail: dict[str, Any] | None) -> bool | None:
    """从商品详情解析包邮状态；无法判断时返回 ``None``。"""
    detail = detail or {}
    item = detail.get("itemDO") or {}
    attribute_map = item.get("attributeMap") or {}
    for key in ("freeShipping", "free_shipping"):
        if key in attribute_map:
            return str(attribute_map[key]).strip().lower() in {"1", "true", "yes"}

    if "transportFee" not in item:
        return None
    try:
        return Decimal(str(item.get("transportFee"))) == 0
    except (InvalidOperation, TypeError, ValueError):
        return None


def extract_seller_credit(detail: dict[str, Any] | None) -> tuple[int | None, str | None]:
    """从商品详情解析闲鱼卖家信用等级，兼容等级数字和信用文本。"""
    seller = (detail or {}).get("sellerDO") or {}
    tag = seller.get("idleFishCreditTag") or {}
    track = tag.get("trackParams") or {}
    raw_level = track.get("sellerLevel")
    try:
        level = int(raw_level)
        if 1 <= level <= 5:
            return level, CREDIT_LABELS[level]
    except (TypeError, ValueError):
        pass

    level_name = str((seller.get("zhimaLevelInfo") or {}).get("levelName") or "").strip()
    normalized = level_name.replace("卖家", "")
    for level, label in CREDIT_LABELS.items():
        if normalized == label or normalized.endswith(label.replace("信用", "")):
            return level, label
    return None, level_name or None


def enrich_from_detail(item: dict[str, Any], detail: dict[str, Any] | None) -> dict[str, Any]:
    """把筛选与入库所需的详情字段补充到解析后的搜索商品。"""
    item = dict(item)
    item["detail"] = detail or None
    detail_free_shipping = extract_free_shipping(detail)
    # 搜索请求已使用官网 filterFreePostage 时，item 中会预先标记为 True；
    # 详情偶尔不返回运费字段，此时不能把官网筛选结果覆盖成未知。
    if detail_free_shipping is not None:
        item["is_free_shipping"] = detail_free_shipping
    credit_level, credit_label = extract_seller_credit(detail)
    item["seller_credit_level"] = credit_level
    item["seller_credit_label"] = credit_label
    seller = (detail or {}).get("sellerDO") or {}
    if not item.get("seller_user_id") and seller.get("sellerId") is not None:
        item["seller_user_id"] = str(seller["sellerId"])
    if not item.get("seller_nick") and seller.get("nick") is not None:
        item["seller_nick"] = str(seller["nick"])
    return item


__all__ = [
    "CREDIT_LABELS",
    "enrich_from_detail",
    "extract_free_shipping",
    "extract_seller_credit",
    "matches_text_filters",
    "normalize_keywords",
]
