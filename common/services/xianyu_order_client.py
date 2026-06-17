"""
闲鱼下单客户端

功能：
1. 使用账号 Cookie 调用闲鱼网页版下单接口（仅需 sign + cookie）
2. order.render 渲染下单信息（拿到 commonData.itemBuyInfo，含收货地址/价格等）
3. order.create 创建订单（拍下），透传 render 返回的 itemBuyInfo 作为 params

安全说明：
- 本客户端只做到"创建订单（拍下）"，不调用 mtop.order.dopay 付款，避免真实扣款。
- 拍下会生成一笔真实未付款订单，请在业务侧确认风险。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from common.services.xianyu_mtop import mtop_call

RENDER_API = "mtop.taobao.idle.trade.order.render"
RENDER_VERSION = "7.0"
CREATE_API = "mtop.taobao.idle.trade.order.create"
CREATE_VERSION = "5.0"


class XianyuOrderClient:
    """闲鱼下单客户端（单账号）"""

    def __init__(self, cookie_id: str, cookies_str: str, owner_id: Optional[int] = None):
        self.cookie_id = cookie_id
        self.cookies_str = cookies_str
        self.owner_id = owner_id

    async def _call(self, api: str, version: str, data: dict) -> Dict[str, Any]:
        """通用 mtop 调用（令牌过期自动刷新重试、Session/风控切换账号）。

        返回 {success, account_invalid, res, error}；令牌刷新后同步更新 self.cookies_str。
        """
        result = await mtop_call(
            self.cookie_id, self.cookies_str, api, version, data,
            owner_id=self.owner_id,
        )
        # 令牌刷新后，回写实例 Cookie，供同一商品的后续调用（render->create）复用
        self.cookies_str = result.get("cookies_str", self.cookies_str)
        return result

    async def render(self, item_id: str) -> Dict[str, Any]:
        """渲染下单信息，返回 {success, account_invalid, item_buy_info, error}。"""
        result = await self._call(RENDER_API, RENDER_VERSION, {"itemId": str(item_id)})
        if not result.get("success"):
            return {"success": False, "account_invalid": result.get("account_invalid", False),
                    "item_buy_info": None, "error": result.get("error")}
        data = (result.get("res") or {}).get("data", {}) or {}
        item_buy_info = (data.get("commonData") or {}).get("itemBuyInfo")
        if not item_buy_info:
            return {"success": False, "account_invalid": False, "item_buy_info": None,
                    "error": "下单渲染缺少 itemBuyInfo（可能商品不可买/缺少收货地址）"}
        return {"success": True, "account_invalid": False, "item_buy_info": item_buy_info, "error": ""}

    async def create(self, item_buy_info: List[dict]) -> Dict[str, Any]:
        """创建订单（拍下），透传 render 返回的 itemBuyInfo。

        Returns: {success, account_invalid, biz_order_id, pay_url, error}
        """
        params_str = json.dumps(item_buy_info, ensure_ascii=False, separators=(",", ":"))
        result = await self._call(CREATE_API, CREATE_VERSION, {"params": params_str})
        if not result.get("success"):
            return {"success": False, "account_invalid": result.get("account_invalid", False),
                    "biz_order_id": None, "pay_url": None, "error": result.get("error")}
        data = (result.get("res") or {}).get("data", {}) or {}
        biz_order_id = data.get("bizOrderIdStr") or data.get("bizOrderId")
        return {
            "success": True,
            "account_invalid": False,
            "biz_order_id": str(biz_order_id) if biz_order_id is not None else None,
            "pay_url": data.get("payUrl"),
            "error": "",
        }

    async def place_order(self, item_id: str) -> Dict[str, Any]:
        """对单个商品下单（render -> create）的完整封装，供下单/采集直接下单复用。

        Returns: {status: 'success'|'account_invalid'|'failed', order_id, error}
        """
        render = await self.render(item_id)
        if not render.get("success"):
            if render.get("account_invalid"):
                return {"status": "account_invalid", "order_id": None, "error": render.get("error")}
            return {"status": "failed", "order_id": None, "error": render.get("error")}

        create = await self.create(render["item_buy_info"])
        if not create.get("success"):
            if create.get("account_invalid"):
                return {"status": "account_invalid", "order_id": None, "error": create.get("error")}
            return {"status": "failed", "order_id": None, "error": create.get("error")}

        return {"status": "success", "order_id": create.get("biz_order_id"), "error": ""}


__all__ = ["XianyuOrderClient"]
