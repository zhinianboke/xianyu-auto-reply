"""
闲鱼卖家后台 editdetail 响应到前端编辑表单的映射。

功能：
1. 把 mtop.idle.pc.backend.idleitem.editdetail 返回的商品详情转成与单品发布表单同构的结构；
2. 反推多规格定义（editdetail 不返回 itemProperties，需从 itemSkuList 的 propertyList 还原）；
3. 反推平台类目、类目属性（成色/品牌等）与发货设置，供编辑弹窗回填。

说明：
- editdetail 的字段值全部是字符串（如 "quantity":"242"、"major":"true"），此处统一做类型转换；
- 价格单位为分（priceInCent），表单使用元，映射时除以 100；
- 输出字段名与素材库接口（ProductMaterial）保持一致，前端可直接复用发布表单组件；
- editdetail 不返回 itemProperties，但会返回 propertyImageList（抓包确认），规格图可原样回填；
  由于 edit 是全量覆盖提交，回填缺失会导致平台原有规格图被清空，故必须映射该字段；
- 平台同一商品只允许一组规格带规格图（抓包确认：两组规格中仅「尺码」的 supportImage 为 true），
  因此 support_image 只会落在真正带图的那一组上。
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from app.services.xianyu_direct_payload import text as _text
from app.services.xianyu_item_snapshot import (
    as_int,
    shipping_method_from_post_fee,
)

# 类目标签使用固定的属性ID，用于把类目标签与普通属性标签区分开
CATEGORY_PROPERTY_ID = "-10000"
# 成色属性ID（抓包确认：20879，值 21456 = 全新）
CONDITION_PROPERTY_ID = "20879"
# 品牌属性ID
BRAND_PROPERTY_ID = "20000"
# 成色兜底来源：commonTagList 里的成色标签键（抓包确认 stuffStatusNew = "全新"）
CONDITION_TAG_KEY = "stuffStatusNew"


def _cent_to_yuan(value: Any) -> float | None:
    """分转元，0 或无效值返回 None。"""
    cents = as_int(value)
    if cents <= 0:
        return None
    return round(cents / 100, 2)


def _property_name_from_properties(properties: str) -> str:
    """从 properties 串里解析属性名。

    editdetail 的 itemLabelExtList 不返回 propertyName，但 properties 形如
    "20879##成色:21456##全新"，中间段冒号前即属性名。

    Args:
        properties: 平台返回的属性串。
    Returns:
        str: 属性名，解析失败返回空串。
    """
    parts = properties.split("##")
    if len(parts) < 2:
        return ""
    return parts[1].split(":")[0].strip()


def _map_labels(detail: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, str]]]:
    """拆分 itemLabelExtList 为「类目标签」与「普通属性标签」。

    Args:
        detail: editdetail 返回的商品详情。
    Returns:
        tuple: (类目标签信息, 属性标签列表)
    """
    category_label: dict[str, str] = {}
    attributes: list[dict[str, str]] = []
    for label in detail.get("itemLabelExtList") or []:
        if not isinstance(label, dict):
            continue
        property_id = _text(label.get("propertyId"))
        properties = _text(label.get("properties"))
        property_name = _text(label.get("propertyName")) or _property_name_from_properties(properties)
        label_text = _text(label.get("text"))
        if property_id == CATEGORY_PROPERTY_ID:
            category_label = {
                "channel_category_id": _text(label.get("channelCateId")) or _text(label.get("valueId")),
                "channel_category_name": label_text,
            }
            continue
        if not property_id or not property_name or not label_text:
            # 提交是全量覆盖，丢弃的属性会从平台商品上消失，必须留下可排查的日志
            logger.warning(
                f"闲鱼商品属性标签信息不完整，编辑时无法回传该属性: item_id={_text(detail.get('itemId'))}, "
                f"property_id={property_id}, property_name={property_name}, text={label_text}"
            )
            continue
        attributes.append(
            {
                "property_id": property_id,
                "property_name": property_name,
                "value_id": _text(label.get("valueId")),
                "value_name": _text(label.get("valueName")) or label_text,
                "text": label_text,
                "properties": properties,
            }
        )
    return category_label, attributes


def _map_property_images(detail: dict[str, Any]) -> dict[tuple[str, str], str]:
    """从 propertyImageList 取出规格图 URL。

    抓包确认 editdetail 会返回 propertyImageList，条目形如
    {"major":"false","property":{"propertyText":"尺码","valueText":"12",...},"url":"https://..."}。
    由于 edit 为全量覆盖提交，不回填该字段会让平台原有规格图被清空。

    Args:
        detail: editdetail 返回的商品详情。
    Returns:
        dict: 以 (规格名, 规格值) 为键的规格图 URL 映射。
    """
    images: dict[tuple[str, str], str] = {}
    for entry in detail.get("propertyImageList") or []:
        if not isinstance(entry, dict):
            continue
        prop = entry.get("property")
        prop = prop if isinstance(prop, dict) else {}
        name = _text(prop.get("propertyText"))
        value = _text(prop.get("valueText")) or _text(prop.get("actualValueText"))
        url = _text(entry.get("url"))
        if name and value and url:
            images[(name, value)] = url
    return images


def _map_specifications(detail: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """从 itemSkuList 反推规格定义与规格组合行。

    Args:
        detail: editdetail 返回的商品详情。
    Returns:
        tuple: (specifications, sku_rows)，单规格商品均为空列表。
    """
    sku_list = detail.get("itemSkuList") or []
    if not isinstance(sku_list, list) or not sku_list:
        return [], []

    # 平台用 propertySortOrder/valueSortOrder 表达规格与规格值的展示顺序，
    # 缺失时退化为「首次出现顺序」（Python 稳定排序保证）
    spec_values: dict[str, list[str]] = {}
    spec_order: dict[str, int] = {}
    value_order: dict[tuple[str, str], int] = {}
    rows: list[dict[str, Any]] = []
    for sku in sku_list:
        if not isinstance(sku, dict):
            continue
        specs: dict[str, str] = {}
        for prop in sku.get("propertyList") or []:
            if not isinstance(prop, dict):
                continue
            name = _text(prop.get("propertyText"))
            value = _text(prop.get("valueText")) or _text(prop.get("actualValueText"))
            if not name or not value:
                continue
            specs[name] = value
            values = spec_values.setdefault(name, [])
            spec_order.setdefault(name, as_int(prop.get("propertySortOrder")))
            value_order.setdefault((name, value), as_int(prop.get("valueSortOrder")))
            if value not in values:
                values.append(value)
        if not specs:
            continue
        rows.append(
            {
                "specs": specs,
                "price": _cent_to_yuan(sku.get("priceInCent")) or 0,
                "stock": as_int(sku.get("quantity")),
            }
        )

    ordered_names = sorted(spec_values, key=lambda n: spec_order.get(n, 0))
    property_images = _map_property_images(detail)
    # 平台只允许一组规格带规格图，取真正带图的那一组；都没有图时所有组的 support_image 均为 False
    image_group = next(
        (
            name
            for name in ordered_names
            if any((name, value) in property_images for value in spec_values[name])
        ),
        "",
    )
    specifications: list[dict[str, Any]] = []
    for name in ordered_names:
        values = sorted(spec_values[name], key=lambda v: value_order.get((name, v), 0))
        specifications.append(
            {
                "name": name,
                "support_image": name == image_group,
                "values": [
                    {"name": value, "image": property_images.get((name, value)) or None}
                    for value in values
                ],
            }
        )
    return specifications, rows


def _map_images(detail: dict[str, Any]) -> list[str]:
    """取出商品主图 URL 列表（主图排在最前，视频条目不纳入图片列表）。"""
    major_urls: list[str] = []
    other_urls: list[str] = []
    for entry in detail.get("imageInfoDOList") or []:
        if not isinstance(entry, dict) or as_int(entry.get("type")) != 0:
            continue
        url = _text(entry.get("url"))
        if not url:
            continue
        if _text(entry.get("major")).lower() == "true":
            major_urls.append(url)
        else:
            other_urls.append(url)
    return major_urls + other_urls


def _map_videos(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """取出平台已有视频，转成编辑弹窗可预览、可原样回传的结构。

    editdetail 的 imageInfoDOList 里 type 非 0 的条目即视频（含 videoUrl/mediaCloudFileId 等）。
    编辑弹窗需要能播放预览（用 videoUrl 作为 url），提交时又要能让后端认出这是平台已有视频
    并原样回传（靠 file_id=mediaCloudFileId 与提交时重新拉取的快照匹配），避免全量覆盖丢视频，
    也避免对平台已有视频做无意义的二次上传。

    Args:
        detail: editdetail 返回的商品详情。
    Returns:
        list: 前端 MaterialVideo 同构的视频列表，无视频时为空列表。
    """
    videos: list[dict[str, Any]] = []
    for entry in detail.get("imageInfoDOList") or []:
        if not isinstance(entry, dict) or as_int(entry.get("type")) == 0:
            continue
        video_url = _text(entry.get("videoUrl"))
        file_id = _text(entry.get("mediaCloudFileId"))
        if not video_url or not file_id:
            continue
        videos.append(
            {
                "url": video_url,
                "path": "",
                "name": "平台视频",
                "file_id": file_id,
                "width": as_int(entry.get("widthSize")) or None,
                "height": as_int(entry.get("heightSize")) or None,
            }
        )
    return videos


def _condition_from_tags(detail: dict[str, Any]) -> str:
    """从 commonTagList 兜底取成色。

    类目属性里缺少成色标签（propertyId=20879）时，平台仍会在 commonTagList 返回
    stuffStatusNew（抓包确认值为「全新」），用它兜底比编造默认值可靠。

    Args:
        detail: editdetail 返回的商品详情。
    Returns:
        str: 成色文案，取不到返回空串。
    """
    for tag in detail.get("commonTagList") or []:
        if isinstance(tag, dict) and _text(tag.get("key")) == CONDITION_TAG_KEY:
            return _text(tag.get("value"))
    return ""


def map_edit_detail_to_form(detail: dict[str, Any]) -> dict[str, Any]:
    """把 editdetail 商品详情转成与单品发布表单同构的编辑表单数据。

    Args:
        detail: editdetail 返回的 data 节点。
    Returns:
        dict: 编辑弹窗回填用的表单数据（价格单位为元）。
    """
    text_dto = detail.get("itemTextDTO") if isinstance(detail.get("itemTextDTO"), dict) else {}
    price_dto = detail.get("itemPriceDTO") if isinstance(detail.get("itemPriceDTO"), dict) else {}
    cat_dto = detail.get("itemCatDTO") if isinstance(detail.get("itemCatDTO"), dict) else {}
    addr_dto = detail.get("itemAddrDTO") if isinstance(detail.get("itemAddrDTO"), dict) else {}
    post_fee = detail.get("itemPostFeeDTO") if isinstance(detail.get("itemPostFeeDTO"), dict) else {}

    category_label, attributes = _map_labels(detail)
    specifications, sku_rows = _map_specifications(detail)
    shipping_method = shipping_method_from_post_fee(post_fee)
    # 成色优先取类目属性标签，缺失时用 commonTagList 兜底，都没有则留空（不编造默认值）
    condition = next(
        (attr["text"] for attr in attributes if attr["property_id"] == CONDITION_PROPERTY_ID), ""
    ) or _condition_from_tags(detail)
    brand = next(
        (attr["text"] for attr in attributes if attr["property_id"] == BRAND_PROPERTY_ID), ""
    )
    category_id = _text(cat_dto.get("catId"))
    category_name = _text(cat_dto.get("catName"))
    # 平台只返回末级分类，分类路径按单级回填，够前端展示与再次提交使用
    category_path = (
        [{"id": category_id, "name": category_name}] if category_id and category_name else []
    )
    # 多规格商品的顶层售价（抓包确认多规格也会返回 priceInCent，取值为最低 SKU 价）；
    # 缺失时按最低 SKU 价兜底，与平台展示口径一致
    price = _cent_to_yuan(price_dto.get("priceInCent"))
    if price is None and sku_rows:
        sku_prices = [row["price"] for row in sku_rows if row["price"] > 0]
        price = min(sku_prices) if sku_prices else None
    # 平台可能残留历史划线价（抓包中售价 1111 元、origPriceInCent 仍是 12 元），
    # 低于或等于售价的划线价没有意义，不回填，避免用户无感提交异常原价
    original_price = _cent_to_yuan(price_dto.get("origPriceInCent"))
    if original_price is not None and price is not None and original_price <= price:
        original_price = None

    return {
        "item_id": _text(detail.get("itemId")),
        "title": _text(text_dto.get("title")),
        "description": _text(text_dto.get("desc")),
        "price": price,
        "original_price": original_price,
        "category": category_name,
        # 多规格库存由各 SKU 提供；单规格忠实回填平台库存（售罄的 0 不能改成 1，否则会把商品重新放量）
        "quantity": 1 if sku_rows else as_int(detail.get("quantity")),
        "images": _map_images(detail),
        "videos": _map_videos(detail),
        "specifications": specifications,
        "sku_rows": sku_rows,
        "platform_category_id": category_id,
        "platform_category_name": category_name,
        "platform_channel_category_id": _text(cat_dto.get("channelCatId"))
        or category_label.get("channel_category_id", ""),
        "platform_channel_category_name": category_label.get("channel_category_name", "")
        or category_name,
        "platform_leaf_id": _text(cat_dto.get("leafId")),
        "platform_tb_category_id": _text(cat_dto.get("tbCatId")),
        "platform_category_path": category_path,
        "platform_attributes": attributes,
        "category_source": "manual",
        "address": _text(addr_dto.get("poiName")),
        "address_expected_text": _text(addr_dto.get("poiName")),
        "shipping_method": shipping_method,
        "postage": round(as_int(post_fee.get("postPriceInCent")) / 100, 2),
        "support_pickup": shipping_method == "none",
        "delivery_method": "express",
        "condition": condition,
        "brand": brand,
    }


__all__ = ["map_edit_detail_to_form"]
