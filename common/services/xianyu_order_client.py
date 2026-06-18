"""
闲鱼下单客户端

功能：
1. 使用账号 Cookie 调用闲鱼网页版下单接口（仅需 sign + cookie）
2. 普通链路：order.render 渲染下单信息（拿到 commonData.itemBuyInfo，含收货地址/价格等）
   -> order.create 创建订单（拍下），透传 render 返回的 itemBuyInfo 作为 params
3. 验货宝链路（yhb）：当普通链路返回"本宝贝为必走验货宝商品，不支持普通链路下单"
   （FAIL_BIZ_ITEM_ONLY_YHB_BUY_APP_LIMIT）时，自动回退到验货宝下单接口：
   address.list.query 取默认收货地址 -> yhb.order.create.render 渲染
   -> yhb.order.create 创建订单（拍下）

安全说明：
- 本客户端只做到"创建订单（拍下）"，不调用 mtop.order.dopay 付款，避免真实扣款。
- 拍下会生成一笔真实未付款订单，请在业务侧确认风险。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger

from common.services.xianyu_mtop import mtop_call

# 普通下单链路
RENDER_API = "mtop.taobao.idle.trade.order.render"
RENDER_VERSION = "7.0"
CREATE_API = "mtop.taobao.idle.trade.order.create"
CREATE_VERSION = "5.0"

# 验货宝（yhb）下单链路
ADDRESS_LIST_API = "mtop.taobao.idle.logistic.address.list.query"
ADDRESS_LIST_VERSION = "1.0"
YHB_RENDER_API = "mtop.alibaba.idle.pc.yhb.order.create.render"
YHB_RENDER_VERSION = "1.0"
YHB_CREATE_API = "mtop.alibaba.idle.pc.yhb.order.create"
YHB_CREATE_VERSION = "1.0"

# 命中以下标志说明该商品必须走验货宝链路下单，普通链路不可用，应回退到 yhb 链路
_YHB_ONLY_MARKERS = (
    "FAIL_BIZ_ITEM_ONLY_YHB_BUY_APP_LIMIT",
    "必走验货宝",
    "ONLY_YHB",
)


def _is_yhb_only_error(error: Optional[str]) -> bool:
    """判断错误信息是否为"必走验货宝商品，不支持普通链路下单"。"""
    if not error:
        return False
    return any(marker in error for marker in _YHB_ONLY_MARKERS)


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
        # 打印下单接口原始返回，便于排查"账号可用却下单失败/账号失效"等问题
        res_json = result.get("res")
        ret = (res_json or {}).get("ret") if isinstance(res_json, dict) else None
        logger.info(
            f"【{self.cookie_id}】下单接口返回 api={api} 请求参数={json.dumps(data, ensure_ascii=False)} "
            f"success={result.get('success')} account_invalid={result.get('account_invalid')} "
            f"error={result.get('error')} ret={ret} res={json.dumps(res_json, ensure_ascii=False)}"
        )
        return result

    # ------------------------------------------------------------------
    # 普通下单链路
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 验货宝（yhb）下单链路
    # ------------------------------------------------------------------
    async def _get_default_address_id(self) -> Dict[str, Any]:
        """查询账号默认收货地址ID（验货宝下单必填）。

        Returns: {success, account_invalid, address_id, error}
        """
        result = await self._call(ADDRESS_LIST_API, ADDRESS_LIST_VERSION, {})
        if not result.get("success"):
            return {"success": False, "account_invalid": result.get("account_invalid", False),
                    "address_id": None, "error": result.get("error")}
        # 响应结构：data.data.addressList[]
        data = (result.get("res") or {}).get("data", {}) or {}
        inner = data.get("data") or {}
        address_list = inner.get("addressList") or []
        if not address_list:
            return {"success": False, "account_invalid": False, "address_id": None,
                    "error": "账号未配置收货地址，验货宝下单需要收货地址"}
        # 优先取状态正常(status=1)的地址，否则取第一条
        chosen = next((a for a in address_list if a.get("status") == 1), address_list[0])
        address_id = chosen.get("addressId")
        if address_id is None:
            return {"success": False, "account_invalid": False, "address_id": None,
                    "error": "收货地址缺少 addressId"}
        return {"success": True, "account_invalid": False, "address_id": address_id, "error": ""}

    async def yhb_render(self, item_id: str) -> Dict[str, Any]:
        """验货宝渲染下单页，返回 {success, account_invalid, yhb_version, buy_quantity, error}。

        渲染用于校验商品可买并获取 yhbVersion / buyQuantity；失败时不阻断下单，
        由调用方使用默认值（yhbVersion=3, buyQuantity=1）继续创建订单。
        """
        result = await self._call(YHB_RENDER_API, YHB_RENDER_VERSION, {"itemId": str(item_id)})
        if not result.get("success"):
            return {"success": False, "account_invalid": result.get("account_invalid", False),
                    "yhb_version": None, "buy_quantity": None, "error": result.get("error")}
        data = (result.get("res") or {}).get("data", {}) or {}
        if data.get("buttonDisable"):
            return {"success": False, "account_invalid": False, "yhb_version": None,
                    "buy_quantity": None, "error": "验货宝下单按钮不可用（商品不可买）"}
        # yhbVersion 形如 "3"，转 int 供 channelData 使用
        try:
            yhb_version = int(data.get("yhbVersion") or 3)
        except (TypeError, ValueError):
            yhb_version = 3
        confirm = data.get("yhbConfirmBuy") or {}
        buy_quantity = confirm.get("buyQuantity") or 1
        return {"success": True, "account_invalid": False, "yhb_version": yhb_version,
                "buy_quantity": buy_quantity, "error": ""}

    async def yhb_create(
        self, item_id: str, buyer_address_id: Any, buy_quantity: int = 1, yhb_version: int = 3
    ) -> Dict[str, Any]:
        """验货宝创建订单（拍下）。

        Returns: {success, account_invalid, biz_order_id, error}
        """
        data = {
            "itemId": str(item_id),
            "optionalPromotionIdValueList": "[]",
            "buyerAddressId": buyer_address_id,
            "buyQuantity": int(buy_quantity or 1),
            "channel": "web",
            "channelData": json.dumps({"yhbVersion": int(yhb_version or 3)}, separators=(",", ":")),
        }
        result = await self._call(YHB_CREATE_API, YHB_CREATE_VERSION, data)
        if not result.get("success"):
            return {"success": False, "account_invalid": result.get("account_invalid", False),
                    "biz_order_id": None, "error": result.get("error")}
        res_data = (result.get("res") or {}).get("data", {}) or {}
        biz_order_id = res_data.get("bizOrderIdStr") or res_data.get("bizOrderId")
        return {
            "success": True,
            "account_invalid": False,
            "biz_order_id": str(biz_order_id) if biz_order_id is not None else None,
            "error": "",
        }

    async def place_order_yhb(self, item_id: str) -> Dict[str, Any]:
        """验货宝链路下单（address.list -> yhb.render -> yhb.create）的完整封装。

        Returns: {status: 'success'|'account_invalid'|'failed', order_id, error}
        """
        # 1) 取默认收货地址（验货宝必填）
        addr = await self._get_default_address_id()
        if not addr.get("success"):
            if addr.get("account_invalid"):
                return {"status": "account_invalid", "order_id": None, "error": addr.get("error")}
            return {"status": "failed", "order_id": None, "error": addr.get("error")}
        buyer_address_id = addr["address_id"]

        # 2) 渲染（best-effort）：失败不阻断，用默认值兜底；账号失效则切号
        yhb_version, buy_quantity = 3, 1
        render = await self.yhb_render(item_id)
        if render.get("success"):
            yhb_version = render.get("yhb_version") or 3
            buy_quantity = render.get("buy_quantity") or 1
        elif render.get("account_invalid"):
            return {"status": "account_invalid", "order_id": None, "error": render.get("error")}
        else:
            logger.warning(
                f"【{self.cookie_id}】商品 {item_id} 验货宝渲染失败，使用默认参数继续下单：{render.get('error')}"
            )

        # 3) 创建订单（拍下）
        create = await self.yhb_create(item_id, buyer_address_id, buy_quantity, yhb_version)
        if not create.get("success"):
            if create.get("account_invalid"):
                return {"status": "account_invalid", "order_id": None, "error": create.get("error")}
            return {"status": "failed", "order_id": None, "error": create.get("error")}
        return {"status": "success", "order_id": create.get("biz_order_id"), "error": ""}

    # ------------------------------------------------------------------
    # 统一下单入口
    # ------------------------------------------------------------------
    async def place_order(self, item_id: str) -> Dict[str, Any]:
        """对单个商品下单的完整封装，供下单/采集直接下单复用。

        流程：普通链路（render -> create）；当命中"必走验货宝"错误时，自动回退到验货宝链路。

        Returns: {status: 'success'|'account_invalid'|'failed', order_id, error}
        """
        render = await self.render(item_id)
        if not render.get("success"):
            if render.get("account_invalid"):
                return {"status": "account_invalid", "order_id": None, "error": render.get("error")}
            # 必走验货宝：回退到 yhb 链路
            if _is_yhb_only_error(render.get("error")):
                logger.info(f"【{self.cookie_id}】商品 {item_id} 为必走验货宝商品，改用验货宝链路下单")
                return await self.place_order_yhb(item_id)
            return {"status": "failed", "order_id": None, "error": render.get("error")}

        create = await self.create(render["item_buy_info"])
        if not create.get("success"):
            if create.get("account_invalid"):
                return {"status": "account_invalid", "order_id": None, "error": create.get("error")}
            # 必走验货宝：回退到 yhb 链路
            if _is_yhb_only_error(create.get("error")):
                logger.info(f"【{self.cookie_id}】商品 {item_id} 为必走验货宝商品，改用验货宝链路下单")
                return await self.place_order_yhb(item_id)
            return {"status": "failed", "order_id": None, "error": create.get("error")}

        return {"status": "success", "order_id": create.get("biz_order_id"), "error": ""}


__all__ = ["XianyuOrderClient"]
