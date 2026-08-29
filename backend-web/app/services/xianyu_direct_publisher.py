"""
闲鱼单品接口发布服务。

功能：
1. 复用公共载荷构造器组装 idleitem.publish 请求；
2. 调用发布接口并解析商品ID/商品链接；
3. 复用公共 mtop 客户端的令牌刷新、Cookie 回写和风控识别。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.services.xianyu_direct_payload import (
    DirectPublishError,
    extract_item_id_from_url as _extract_item_id_from_url,
    find_item_reference as _find_item_reference,
)
from app.services.xianyu_item_payload_builder import build_item_payload
from common.services.xianyu_mtop import mtop_call
from common.utils.xianyu_utils import canonical_goofish_item_url


PUBLISH_API = "mtop.idle.pc.backend.idleitem.publish"
SELLER_ORIGIN = "https://seller.goofish.com"
SELLER_REFERER = "https://seller.goofish.com/?site=COMMONPRO"


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
        try:
            payload, cookie = await build_item_payload(
                item_data,
                cookie,
                account_id,
                owner_id,
                static_root=self.static_root,
            )
        except DirectPublishError as exc:
            if not exc.account_invalid:
                raise
            # 媒体上传时判定账号失效：保持原有返回结构，交由上层标记账号状态。
            return {
                "success": False,
                "message": str(exc),
                "item_id": None,
                "item_url": None,
                "account_invalid": True,
                "cookies_str": cookie,
            }

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
