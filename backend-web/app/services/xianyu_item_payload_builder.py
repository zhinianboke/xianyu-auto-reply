"""
闲鱼卖家后台（鱼小铺）商品载荷构造器。

功能：
1. 集中构造 idleitem.publish（发布）与 idleitem.edit（编辑）共用的 inputJson 载荷；
2. 上传商品图片/视频封面、按高德解析宝贝所在地、组装平台分类与属性标签；
3. 编辑场景可传入平台 editdetail 快照，未改动的图片/地址/运费直接复用，避免重传与重解析。

说明：
- 本文件从 xianyu_direct_publisher.py 抽取而来，行为与原发布逻辑保持一致；
- 编辑接口与发布接口的 inputJson 字段集完全相同（抓包已确认），故共用同一构造器。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.services.amap_inputtips_service import AmapInputTipsError, AmapInputTipsService
from app.services.xianyu_direct_payload import (
    DirectPublishError,
    build_sku_payload as _build_sku_payload,
    price_in_cent as _price_in_cent,
    text as _text,
)
from app.services.xianyu_item_snapshot import (
    as_int,
    normalize_snapshot_post_fee,
    snapshot_address_if_unchanged,
    snapshot_image_index,
    snapshot_post_fee_unchanged,
    snapshot_user_rights,
    snapshot_video_index,
    snapshot_video_items,
)
from common.services.xianyu_publish_media import PublishMediaError, upload_publish_image
from common.services.xianyu_publish_video import PublishVideoError, upload_publish_videos

# 平台一次最多接收 9 张商品主图
MAX_IMAGE_COUNT = 9


def _location_to_gps(location: str) -> str:
    """将高德经纬度转为闲鱼接口所需的纬度,经度。"""
    parts = [part.strip() for part in location.split(",")]
    if len(parts) != 2:
        raise DirectPublishError("宝贝所在地缺少有效坐标，请重新选择地址")
    try:
        longitude = float(parts[0])
        latitude = float(parts[1])
    except ValueError as exc:
        raise DirectPublishError("宝贝所在地坐标格式不正确，请重新选择地址") from exc
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        raise DirectPublishError("宝贝所在地坐标无效，请重新选择地址")
    return f"{latitude:.6f},{longitude:.6f}"


def _address_match_score(tip: dict[str, Any], expected_text: str) -> tuple[int, int]:
    """按用户选择时保存的期望文本优先匹配高德候选。"""
    if not expected_text:
        return (3, 0)
    expected = expected_text.replace(" ", "")
    candidate = _text(tip.get("expected_text")) or " / ".join(
        value for value in (_text(tip.get("name")), _text(tip.get("address"))) if value
    )
    candidate = candidate.replace(" ", "")
    if candidate == expected:
        return (0, len(candidate))
    if candidate.startswith(expected):
        return (1, len(candidate))
    if expected in candidate:
        return (2, candidate.find(expected))
    return (4, len(candidate))


async def _resolve_item_address(item_data: dict[str, Any]) -> dict[str, str]:
    """重新请求高德 inputtips，将素材文本地址解析为闲鱼发布地址结构。"""
    address = _text(item_data.get("address"))
    if not address:
        raise DirectPublishError("请先选择带有效坐标的宝贝所在地")
    expected_text = _text(item_data.get("address_expected_text"))
    try:
        result = await AmapInputTipsService().search(address)
    except AmapInputTipsError as exc:
        raise DirectPublishError(str(exc)) from exc

    tips = result.get("tips") if isinstance(result, dict) else []
    valid_tips = [
        tip for tip in tips if isinstance(tip, dict)
        and _text(tip.get("id")) and _text(tip.get("adcode")) and _text(tip.get("location"))
    ]
    if not valid_tips:
        raise DirectPublishError("宝贝所在地未返回POI编号、行政区划或坐标，请重新选择地址")
    selected = min(valid_tips, key=lambda tip: _address_match_score(tip, expected_text))
    return {
        "divisionId": _text(selected.get("adcode")),
        "gps": _location_to_gps(_text(selected.get("location"))),
        "poiId": _text(selected.get("id")),
        "poiName": _text(selected.get("name")),
    }


def _build_category_label(item_data: dict[str, Any]) -> dict[str, Any]:
    """构造抓包中的分类属性标签，确保平台分类和分类ID一同提交。"""
    channel_id = _text(item_data.get("platform_channel_category_id"))
    channel_name = _text(item_data.get("platform_channel_category_name"))
    category_name = _text(item_data.get("platform_category_name"))
    tb_cat_id = _text(item_data.get("platform_tb_category_id"))
    if not channel_id or not channel_name or not tb_cat_id:
        raise DirectPublishError("请先根据商品描述重新选择完整的平台商品分类")
    return {
        "channelCateName": channel_name,
        "valueId": None,
        "channelCateId": channel_id,
        "valueName": None,
        "tbCatId": tb_cat_id,
        "subPropertyId": None,
        "labelType": "common",
        "subValueId": None,
        "labelId": None,
        "propertyName": "分类",
        "isUserClick": "1",
        "isUserCancel": None,
        "from": "newPublishChoice",
        "propertyId": "-10000",
        "labelFrom": "newPublish",
        "text": category_name or channel_name,
        "properties": f"-10000##分类:{channel_id}##{category_name or channel_name}",
    }


def _build_attribute_labels(item_data: dict[str, Any]) -> list[dict[str, Any]]:
    """转换前端保存的属性标签，未知或不完整标签不提交给平台。"""
    labels = [_build_category_label(item_data)]
    for attribute in item_data.get("platform_attributes") or []:
        if not isinstance(attribute, dict) or _text(attribute.get("property_name")) == "分类":
            continue
        property_id = _text(attribute.get("property_id"))
        property_name = _text(attribute.get("property_name"))
        value_id = _text(attribute.get("value_id"))
        value_name = _text(attribute.get("value_name")) or _text(attribute.get("text"))
        if not property_id or not property_name or not value_name:
            continue
        labels.append(
            {
                "channelCateName": _text(item_data.get("platform_channel_category_name")) or None,
                "valueId": value_id,
                "channelCateId": _text(item_data.get("platform_channel_category_id")),
                "valueName": value_name,
                "tbCatId": _text(item_data.get("platform_tb_category_id")),
                "subPropertyId": None,
                "labelType": "common",
                "subValueId": None,
                "labelId": None,
                "propertyName": property_name,
                "isUserClick": "1",
                "isUserCancel": None,
                "from": "newPublishChoice",
                "propertyId": property_id,
                "labelFrom": "newPublish",
                "text": value_name,
                "properties": _text(attribute.get("properties"))
                or f"{property_id}##{property_name}:{value_id or ''}##{value_name}",
            }
        )
    return labels


def _build_post_fee(item_data: dict[str, Any]) -> dict[str, bool]:
    """转换已由抓包确认的包邮和仅自提发货方式。"""
    shipping_method = _text(item_data.get("shipping_method")) or "free"
    if shipping_method == "free":
        return {"canFreeShipping": True, "supportFreight": True, "onlyTakeSelf": False}
    if shipping_method == "none":
        return {"canFreeShipping": False, "supportFreight": False, "onlyTakeSelf": True}
    raise DirectPublishError("当前接口抓包未包含非包邮运费载荷，请改为包邮或无需邮寄后发布")


def _resolve_post_fee(item_data: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """编辑时发货设置未改动则复用平台快照，否则按发布逻辑重新构造。

    Args:
        item_data: 前端表单数据。
        snapshot: editdetail 原始详情，发布场景为 None。
    Returns:
        dict: 可直接提交的 itemPostFeeDTO。
    """
    if snapshot:
        snapshot_post_fee = snapshot.get("itemPostFeeDTO")
        if snapshot_post_fee_unchanged(item_data, snapshot_post_fee):
            return normalize_snapshot_post_fee(snapshot_post_fee)
    return _build_post_fee(item_data)


async def _resolve_address(
    item_data: dict[str, Any], snapshot: dict[str, Any] | None
) -> dict[str, Any]:
    """编辑时宝贝所在地未改动则复用平台快照，否则重新请求高德解析。

    Args:
        item_data: 前端表单数据。
        snapshot: editdetail 原始详情，发布场景为 None。
    Returns:
        dict: 可直接提交的 itemAddrDTO。
    """
    reused = snapshot_address_if_unchanged(item_data, snapshot)
    if reused is not None:
        return reused
    return await _resolve_item_address(item_data)


def _resolve_quantity(item_data: dict[str, Any]) -> int:
    """解析单规格商品的提交库存。

    编辑场景必须允许 0：平台售罄商品的 quantity 就是 0，擅自改成 1
    会把商品重新放量。表单未提供该字段时（发布场景）按 1 处理。

    Args:
        item_data: 前端表单数据。
    Returns:
        int: 0~999999 之间的库存值。
    """
    raw = item_data.get("quantity")
    if raw is None or _text(raw) == "":
        return 1
    return max(0, min(as_int(raw, 1), 999999))


def _resolve_user_rights(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    """解析要提交的服务承诺开关。

    编辑场景复用平台快照，避免全量覆盖时把卖家已开启的极速发货/不符退款关掉；
    发布场景（无快照）沿用抓包中的默认值：三项均关闭。

    Args:
        snapshot: editdetail 原始详情，发布场景为 None。
    Returns:
        list: userRightsProtocols 列表。
    """
    reused = snapshot_user_rights(snapshot)
    if reused:
        return reused
    return [
        {"enable": False, "serviceCode": "FAST_DELIVERY_48_HOUR"},
        {"enable": False, "serviceCode": "FAST_DELIVERY_24_HOUR"},
        {"enable": False, "serviceCode": "NONCONFORMITY_FREE_REFUND"},
    ]


async def build_item_payload(
    item_data: dict[str, Any],
    cookie: str,
    account_id: str,
    owner_id: int | None,
    *,
    static_root: str | Path | None = None,
    snapshot: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    """构造 idleitem.publish / idleitem.edit 共用的 inputJson 载荷。

    Args:
        item_data: 前端表单数据（标题、描述、图片、价格、规格、分类、发货设置等）。
        cookie: 账号 Cookie 字符串。
        account_id: 闲鱼账号标识。
        owner_id: 账号所属用户ID，媒体上传/令牌刷新回写使用。
        static_root: 本地静态文件根目录，用于解析 /static/... 图片路径。
        snapshot: 编辑场景传入平台 editdetail 原始详情；发布场景为 None。
            传入后，未改动的图片/视频/宝贝所在地/发货设置会直接复用平台数据。
    Returns:
        tuple: (payload, cookie) —— cookie 可能因媒体上传刷新令牌而更新。
    Raises:
        DirectPublishError: 表单校验失败或媒体上传失败（账号失效时 account_invalid=True）。
    """
    title = _text(item_data.get("title"))
    description = _text(item_data.get("description"))
    if not title or not description:
        raise DirectPublishError("商品标题和商品描述不能为空")
    item_properties, item_sku_list, property_image_sources, is_multi_spec = _build_sku_payload(item_data)
    images = [value for value in item_data.get("images") or [] if _text(value)]
    if not images:
        raise DirectPublishError("请至少上传一张商品图片")
    labels = _build_attribute_labels(item_data)
    category_info = {
        "catId": _text(item_data.get("platform_category_id")),
        "catName": _text(item_data.get("platform_category_name")),
        "channelCatId": _text(item_data.get("platform_channel_category_id")),
        "leafId": _text(item_data.get("platform_leaf_id")),
        "tbCatId": _text(item_data.get("platform_tb_category_id")),
    }
    missing_category_fields = [
        field for field in ("catId", "channelCatId", "tbCatId") if not category_info[field]
    ]
    if missing_category_fields:
        field_names = {
            "catId": "末级分类ID",
            "channelCatId": "频道分类ID",
            "tbCatId": "淘宝分类ID",
        }
        raise DirectPublishError(
            "平台商品分类信息不完整，缺少 "
            f"{', '.join(field_names[field] for field in missing_category_fields)}，请重新选择分类"
        )
    resolved_address = await _resolve_address(item_data, snapshot)

    video_items: list[dict[str, Any]] = []
    raw_videos = item_data.get("videos")
    if raw_videos is None:
        # 编辑请求未携带 videos 字段（旧版前端）：回退平台快照，保持原有视频不丢。
        video_items = snapshot_video_items(snapshot)
    else:
        # 前端已接管视频：videos 即最终视频集（空列表=用户删光，不再回退快照）。
        # 已在平台的视频凭 file_id 命中快照原样回传，不重复上传；其余按新增本地视频上传。
        snapshot_videos = snapshot_video_index(snapshot)
        reuse_videos: list[dict[str, Any]] = []
        upload_sources: list[Any] = []
        for video in raw_videos:
            file_id = (
                _text(video.get("file_id") or video.get("mediaCloudFileId"))
                if isinstance(video, dict)
                else ""
            )
            existing = snapshot_videos.get(file_id) if file_id else None
            if existing is not None:
                reuse_videos.append(dict(existing))
            else:
                upload_sources.append(video)
        video_items = reuse_videos
        if upload_sources:
            try:
                uploaded_videos, cookie = await upload_publish_videos(
                    upload_sources,
                    cookie,
                    account_id,
                    owner_id,
                    static_root=static_root,
                )
            except PublishVideoError as exc:
                raise DirectPublishError(
                    f"视频上传失败：{exc}", account_invalid=exc.account_invalid
                ) from exc
            video_items = reuse_videos + uploaded_videos
        # 复用的平台视频带原有 major、上传的视频按批内序号置 major，
        # 两者混在一起会出现多个 major，按最终顺序重置为「仅第一个为主」
        for index, video in enumerate(video_items):
            video["major"] = index == 0


    snapshot_images = snapshot_image_index(snapshot)
    image_items: list[dict[str, Any]] = []
    for index, image in enumerate(images[:MAX_IMAGE_COUNT], 1):
        image_url = _text(image)
        existing = snapshot_images.get(image_url)
        if existing is not None:
            # 图片未改动，直接复用平台已有条目（含宽高信息），不再重复上传。
            uploaded = dict(existing)
        else:
            try:
                uploaded = await upload_publish_image(
                    image_url,
                    cookie,
                    static_root=static_root,
                )
            except PublishMediaError as exc:
                raise DirectPublishError(f"第 {index} 张图片上传失败：{exc}") from exc
        uploaded["major"] = index == 1
        image_items.append(uploaded)

    property_image_list: list[dict[str, Any]] = []
    if is_multi_spec and property_image_sources:
        image_by_property: dict[tuple[str, str], dict[str, Any]] = {}
        for image_source in property_image_sources:
            property_name = image_source["property_name"]
            property_value = image_source["property_value"]
            source_url = _text(image_source["source"])
            existing = snapshot_images.get(source_url)
            if existing is not None:
                uploaded = dict(existing)
            else:
                # 平台原有规格图会走到这里重新上传：editdetail 的 propertyImageList 只给 URL
                # 不给宽高，直接复用会得到编造的尺寸，因此按原图重新上传拿真实宽高。
                try:
                    uploaded = await upload_publish_image(
                        image_source["source"],
                        cookie,
                        static_root=static_root,
                    )
                except PublishMediaError as exc:
                    raise DirectPublishError(
                        f"规格 {property_name}={property_value} 图片上传失败：{exc}"
                    ) from exc
            property_image = dict(uploaded)
            property_image.pop("major", None)
            image_by_property[(property_name, property_value)] = property_image
            property_image_list.append(
                {
                    "property": {
                        "propertyText": property_name,
                        "valueText": property_value,
                    },
                    "url": property_image["url"],
                }
            )
        for item_property in item_properties:
            for property_value in item_property.get("propertyValues") or []:
                key = (
                    _text(item_property.get("propertyName")),
                    _text(property_value.get("propertyValue")),
                )
                image = image_by_property.get(key)
                if image:
                    property_value["propertyValueImg"] = image

    payload: dict[str, Any] = {
        "freebies": False,
        "itemTypeStr": "b",
        # 抓包中的多规格商品顶层数量为字符串 1，实际库存由 itemSkuList 提供。
        "quantity": "1" if is_multi_spec else _resolve_quantity(item_data),
        "simpleItem": "true",
        "imageInfoDOList": video_items + image_items,
        "itemTextDTO": {"desc": description, "title": title, "titleDescSeparate": False},
        "itemLabelExtList": labels,
        "itemProperties": item_properties,
        "userRightsProtocols": _resolve_user_rights(snapshot),
        "itemPostFeeDTO": _resolve_post_fee(item_data, snapshot),
        "itemAddrDTO": resolved_address,
        "itemSkuList": item_sku_list,
        "defaultPrice": False,
        "itemPriceDTO": (
            {}
            if is_multi_spec
            else {
                "origPriceInCent": _price_in_cent(
                    item_data.get("original_price") or item_data.get("price"), "原价"
                ),
                "priceInCent": _price_in_cent(item_data.get("price"), "售价"),
            }
        ),
        "uniqueCode": f"{int(time.time() * 1000)}{account_id[-4:]}",
        "sourceId": "pcBackendPublish",
        "bizcode": "pcMainPublish",
        "publishScene": "pcBackendPublish",
    }
    if property_image_list:
        payload["propertyImageList"] = property_image_list
    if not is_multi_spec:
        payload.pop("itemProperties", None)
        payload.pop("itemSkuList", None)
    payload["itemCatDTO"] = category_info
    return payload, cookie


__all__ = ["DirectPublishError", "build_item_payload"]
