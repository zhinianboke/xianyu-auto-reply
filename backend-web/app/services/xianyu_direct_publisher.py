"""
闲鱼单品接口发布服务。

功能：
1. 按卖家工作台抓包构造 idleitem.publish 请求；
2. 上传本地商品图片和视频封面、解析高德所在地并组装平台分类；
3. 复用公共 mtop 客户端的令牌刷新、Cookie 回写和风控识别。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

from app.services.amap_inputtips_service import AmapInputTipsError, AmapInputTipsService
from app.services.xianyu_direct_payload import (
    DirectPublishError,
    build_sku_payload as _build_sku_payload,
    extract_item_id_from_url as _extract_item_id_from_url,
    find_item_reference as _find_item_reference,
    price_in_cent as _price_in_cent,
    text as _text,
)
from common.services.xianyu_mtop import mtop_call
from common.services.xianyu_publish_media import PublishMediaError, upload_publish_image
from common.services.xianyu_publish_video import PublishVideoError, upload_publish_videos
from common.utils.xianyu_utils import canonical_goofish_item_url


PUBLISH_API = "mtop.idle.pc.backend.idleitem.publish"
SELLER_ORIGIN = "https://seller.goofish.com"
SELLER_REFERER = "https://seller.goofish.com/?site=COMMONPRO"


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


class XianyuDirectPublisher:
    """使用闲鱼卖家工作台 mtop 接口发布单个商品。"""

    def __init__(self, static_root: str | Path | None = None):
        self.static_root = Path(static_root) if static_root else None

    async def publish_item(
        self,
        item_data: dict[str, Any],
        cookie: str,
        account_id: str,
        owner_id: int | None,
    ) -> dict[str, Any]:
        """上传媒体并调用最终发布接口，返回统一发布结果。"""
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
        resolved_address = await _resolve_item_address(item_data)

        video_items: list[dict[str, Any]] = []
        if item_data.get("videos"):
            try:
                video_items, cookie = await upload_publish_videos(
                    item_data.get("videos") or [],
                    cookie,
                    account_id,
                    owner_id,
                    static_root=self.static_root,
            )
            except PublishVideoError as exc:
                if exc.account_invalid:
                    return {
                        "success": False,
                        "message": f"视频上传失败：{exc}",
                        "item_id": None,
                        "item_url": None,
                        "account_invalid": True,
                        "cookies_str": cookie,
                    }
                raise DirectPublishError(f"视频上传失败：{exc}") from exc

        image_items: list[dict[str, Any]] = []
        for index, image in enumerate(images[:9], 1):
            try:
                uploaded = await upload_publish_image(
                    _text(image),
                    cookie,
                    static_root=self.static_root,
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
                try:
                    uploaded = await upload_publish_image(
                        image_source["source"],
                        cookie,
                        static_root=self.static_root,
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

        payload = {
            "freebies": False,
            "itemTypeStr": "b",
            # 抓包中的多规格商品顶层数量为字符串 1，实际库存由 itemSkuList 提供。
            "quantity": "1" if is_multi_spec else max(1, min(int(item_data.get("quantity") or 1), 999999)),
            "simpleItem": "true",
            "imageInfoDOList": video_items + image_items,
            "itemTextDTO": {"desc": description, "title": title, "titleDescSeparate": False},
            "itemLabelExtList": labels,
            "itemProperties": item_properties,
            "userRightsProtocols": [
                {"enable": False, "serviceCode": "FAST_DELIVERY_48_HOUR"},
                {"enable": False, "serviceCode": "FAST_DELIVERY_24_HOUR"},
                {"enable": False, "serviceCode": "NONCONFORMITY_FREE_REFUND"},
            ],
            "itemPostFeeDTO": _build_post_fee(item_data),
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
        response = await mtop_call(
            account_id=account_id,
            cookies_str=cookie,
            api=PUBLISH_API,
            version="1.0",
            data={"inputJson": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
            owner_id=owner_id,
            extra_params={
                "idle_site_biz_code": "COMMONPRO",
                "spm_cnt": "a21107h.42826273.0.0",
            },
            origin=SELLER_ORIGIN,
            referer=SELLER_REFERER,
            extra_headers={"idle_site_biz_code": "COMMONPRO"},
        )
        if not response.get("success"):
            logger.error(
                f"闲鱼商品发布接口失败完整返回: account_id={account_id}, "
                f"response={json.dumps(response, ensure_ascii=False, default=str)}"
            )
            return {
                "success": False,
                "message": f"闲鱼接口发布失败：{response.get('error') or '未知错误'}",
                "item_id": None,
                "item_url": None,
                "account_invalid": bool(response.get("account_invalid")),
                "cookies_str": response.get("cookies_str") or cookie,
            }
        item_id, item_url = _find_item_reference(response.get("res"))
        if item_id:
            # 发布接口可能返回旧版 /item/{id} 或带协议地址，统一改成当前网页格式。
            item_url = canonical_goofish_item_url(item_id)
        elif item_url:
            extracted_id = _extract_item_id_from_url(item_url)
            if extracted_id:
                item_id = extracted_id
                item_url = canonical_goofish_item_url(extracted_id)
        logger.info(f"闲鱼商品发布接口调用成功: account_id={account_id}, item_id={item_id or '未返回'}")
        return {
            "success": True,
            "message": "商品发布成功",
            "item_id": item_id,
            "item_url": item_url,
            "account_invalid": False,
            "cookies_str": response.get("cookies_str") or cookie,
        }


__all__ = ["DirectPublishError", "XianyuDirectPublisher"]
