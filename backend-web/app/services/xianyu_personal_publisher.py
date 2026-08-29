"""
闲鱼普通卖家单品接口发布服务。

功能：
1. 按普通卖家网页发布抓包构造 idleitem.publish 请求；
2. 复用现有分类、地址、媒体上传与响应解析公共逻辑；
3. 明确禁止普通卖家提交鱼小铺多规格库存载荷。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

from app.services.xianyu_direct_payload import (
    DirectPublishError,
    extract_item_id_from_url,
    find_item_reference,
    price_in_cent,
    text,
)
from app.services.xianyu_item_payload_builder import _build_attribute_labels, _resolve_item_address
from common.services.xianyu_mtop import mtop_call
from common.services.xianyu_publish_media import PublishMediaError, upload_publish_image
from common.services.xianyu_publish_video import PublishVideoError, upload_publish_videos
from common.utils.xianyu_utils import canonical_goofish_item_url


PUBLISH_API = "mtop.idle.pc.idleitem.publish"
PUBLISH_ORIGIN = "https://www.goofish.com"
PUBLISH_REFERER = "https://www.goofish.com/publish"


def _build_personal_post_fee(item_data: dict[str, Any]) -> dict[str, Any]:
    """按普通卖家网页发布组件的字段规则构造发货配置。"""
    shipping_method = text(item_data.get("shipping_method")) or "free"
    only_take_self = bool(item_data.get("support_pickup"))
    if shipping_method == "free":
        return {"canFreeShipping": True, "supportFreight": True, "onlyTakeSelf": only_take_self}
    if shipping_method == "distance":
        return {
            "canFreeShipping": False,
            "supportFreight": True,
            "onlyTakeSelf": only_take_self,
            "templateId": "-100",
        }
    if shipping_method == "fixed":
        postage = float(item_data.get("postage") or 0)
        if postage < 0 or postage > 1000:
            raise DirectPublishError("宝贝运费必须在0到1000元之间")
        return {
            "canFreeShipping": False,
            "supportFreight": True,
            "onlyTakeSelf": only_take_self,
            "postPriceInCent": str(round(postage * 100)),
            "templateId": "0",
        }
    if shipping_method == "none":
        return {
            "canFreeShipping": False,
            "supportFreight": False,
            "onlyTakeSelf": only_take_self,
            "templateId": "0",
        }
    raise DirectPublishError("普通卖家发布不支持运费模板，请选择包邮、按距离计费、一口价或无需邮寄")


class XianyuPersonalPublisher:
    """使用闲鱼普通卖家网页 mtop 接口发布单个商品。"""

    def __init__(self, static_root: str | Path | None = None):
        self.static_root = Path(static_root) if static_root else None

    async def publish_item(
        self,
        item_data: dict[str, Any],
        cookie: str,
        account_id: str,
        owner_id: int | None,
    ) -> dict[str, Any]:
        """
        上传媒体并调用普通卖家发布接口。

        Args:
            item_data: 前端提交的商品数据。
            cookie: 账号 Cookie。
            account_id: 闲鱼账号标识。
            owner_id: 账号所属用户 ID。
        Returns:
            统一的发布结果与可能刷新的 Cookie。
        """
        title = text(item_data.get("title"))
        description = text(item_data.get("description"))
        if not title or not description:
            raise DirectPublishError("商品标题和商品描述不能为空")
        if item_data.get("specifications") or item_data.get("sku_rows"):
            raise DirectPublishError("当前账号未开通鱼小铺，不能发布多规格和独立库存商品")
        # 发货方式先校验，避免运费模板等不支持配置在媒体上传后才失败。
        post_fee = _build_personal_post_fee(item_data)

        images = [value for value in item_data.get("images") or [] if text(value)]
        if not images:
            raise DirectPublishError("请至少上传一张商品图片")
        labels = _build_attribute_labels(item_data)
        category_info = {
            "catId": text(item_data.get("platform_category_id")),
            "catName": text(item_data.get("platform_category_name")),
            "channelCatId": text(item_data.get("platform_channel_category_id")),
            "tbCatId": text(item_data.get("platform_tb_category_id")),
        }
        missing_fields = [field for field in ("catId", "channelCatId", "tbCatId") if not category_info[field]]
        if missing_fields:
            names = {"catId": "末级分类ID", "channelCatId": "频道分类ID", "tbCatId": "淘宝分类ID"}
            raise DirectPublishError(
                "平台商品分类信息不完整，缺少 "
                f"{', '.join(names[field] for field in missing_fields)}，请重新选择分类"
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
                uploaded = await upload_publish_image(text(image), cookie, static_root=self.static_root)
            except PublishMediaError as exc:
                raise DirectPublishError(f"第 {index} 张图片上传失败：{exc}") from exc
            uploaded["major"] = index == 1
            image_items.append(uploaded)

        payload = {
            "freebies": False,
            "itemTypeStr": "b",
            "quantity": "1",
            "simpleItem": "true",
            "imageInfoDOList": video_items + image_items,
            "itemTextDTO": {"desc": description, "title": title, "titleDescSeparate": False},
            "itemLabelExtList": labels,
            "itemPriceDTO": {
                "origPriceInCent": price_in_cent(
                    item_data.get("original_price") or item_data.get("price"), "原价"
                ),
                "priceInCent": price_in_cent(item_data.get("price"), "售价"),
            },
            "userRightsProtocols": [],
            "itemPostFeeDTO": post_fee,
            "itemAddrDTO": resolved_address,
            "defaultPrice": False,
            "itemCatDTO": category_info,
            "uniqueCode": f"{int(time.time() * 1000)}{account_id[-4:]}",
            "sourceId": "pcMainPublish",
            "bizcode": "pcMainPublish",
            "publishScene": "pcMainPublish",
        }
        response = await mtop_call(
            account_id=account_id,
            cookies_str=cookie,
            api=PUBLISH_API,
            version="1.0",
            data=payload,
            owner_id=owner_id,
            extra_params={"spm_cnt": "a21ybx.publish.0.0"},
            origin=PUBLISH_ORIGIN,
            referer=PUBLISH_REFERER,
        )
        if not response.get("success"):
            logger.error(
                f"闲鱼普通卖家发布接口失败完整返回: account_id={account_id}, "
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

        item_id, item_url = find_item_reference(response.get("res"))
        if item_id:
            item_url = canonical_goofish_item_url(item_id)
        elif item_url:
            extracted_id = extract_item_id_from_url(item_url)
            if extracted_id:
                item_id = extracted_id
                item_url = canonical_goofish_item_url(extracted_id)
        logger.info(f"闲鱼普通卖家发布接口调用成功: account_id={account_id}, item_id={item_id or '未返回'}")
        return {
            "success": True,
            "message": "商品发布成功",
            "item_id": item_id,
            "item_url": item_url,
            "account_invalid": False,
            "cookies_str": response.get("cookies_str") or cookie,
        }


__all__ = ["XianyuPersonalPublisher"]
