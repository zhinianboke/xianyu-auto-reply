"""
闲鱼卖家平台（鱼小铺）商品列表客户端。

功能：
1. 使用账号 Cookie 调用卖家专业版商品列表接口 mtop.alibaba.idle.seller.pc.common.item.search
2. 将卖家平台返回的商品字段映射为与个人版一致的商品结构，复用统一入库逻辑
3. 接口/方法签名与 common.utils.item_info_manager.ItemInfoManager 对齐（鸭子类型），
   使商品同步的翻页/入库调用方无需区分数据源

说明：
- 卖家平台商品在 seller.goofish.com，需带对应 Origin/Referer 才能通过登录态校验
- 仅抓取在售商品（itemStatus="0"），与个人版 groupName='在售' 行为保持一致
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger

from common.services.xianyu_mtop import mtop_call

# 卖家平台商品列表接口（阿里 mtop）
SELLER_ITEM_LIST_API = "mtop.alibaba.idle.seller.pc.common.item.search"
SELLER_ITEM_LIST_VERSION = "1.0"
# 卖家平台商品信息更新接口（改价/改库存），单规格与多规格共用此接口
SELLER_ITEM_UPDATE_API = "mtop.alibaba.idle.seller.pc.item.info.update"
SELLER_ITEM_UPDATE_VERSION = "1.0"
# 卖家平台域名，缺失时接口会因登录态校验失败
SELLER_ORIGIN = "https://seller.goofish.com"
SELLER_REFERER = "https://seller.goofish.com/?site=COMMONPRO"
# 卖家平台商品搜索业务类型
SELLER_BIZ_TYPE = "commonPro"
# 仅抓在售（与个人版 groupName='在售' 一致）
SELLER_ITEM_STATUS_ON_SALE = "0"
# 专业版卖家（鱼小铺 COMMONPRO）鉴权请求头：缺失时服务端返回 FAIL_BIZ_IDLE_USER_UNAUTHORIZED::无权限访问。
# 抓包中列表与改价接口均携带此头以声明专业版卖家上下文。
SELLER_BIZ_HEADERS = {
    "idle_site_biz_code": "COMMONPRO",
    "idle_user_group_member_id": "",
}


class SellerItemInfoManager:
    """鱼小铺（卖家平台）商品列表抓取器，接口与 ItemInfoManager 对齐。"""

    def __init__(self, account_id: str, cookie: str, owner_id: Optional[int] = None) -> None:
        """
        Args:
            account_id: 闲鱼账号标识。
            cookie: 账号 Cookie 字符串。
            owner_id: 账号所属用户 ID，令牌刷新后回写 Cookie 使用。
        """
        self.cookie_id = account_id
        self.account_id = account_id
        self.cookies_str = cookie
        self.owner_id = owner_id

    async def get_item_list_info(
        self,
        page_number: int,
        page_size: int,
        myid: Any = None,
    ) -> dict:
        """抓取指定页的卖家平台在售商品，返回与个人版一致的商品结构。

        Args:
            page_number: 页码，从 1 开始。
            page_size: 每页数量。
            myid: 兼容 ItemInfoManager 的参数，本接口不使用。
        Returns:
            dict: {success, items, page_number, page_size, current_count, has_more, raw_data}
                  或 {success: False, error/message}
        """
        data = {
            "pageNo": page_number,
            "pageSize": page_size,
            "bizType": SELLER_BIZ_TYPE,
            "searchRequest": "{}",
            "itemStatus": SELLER_ITEM_STATUS_ON_SALE,
        }

        response = await mtop_call(
            account_id=self.account_id,
            cookies_str=self.cookies_str,
            api=SELLER_ITEM_LIST_API,
            version=SELLER_ITEM_LIST_VERSION,
            data=data,
            owner_id=self.owner_id,
            extra_params={
                "spm_cnt": "a21107h.42826273.0.0",
                "needLoginPC": "true",
                "accountSite": "xianyu",
            },
            extra_headers=SELLER_BIZ_HEADERS,
            origin=SELLER_ORIGIN,
            referer=SELLER_REFERER,
        )

        # mtop_call 可能刷新令牌并回写数据库，这里同步最新 Cookie 供后续翻页复用
        self.cookies_str = response.get("cookies_str") or self.cookies_str

        if not response.get("success"):
            error_msg = response.get("error") or "获取鱼小铺商品失败"
            logger.error(f"【{self.account_id}】卖家平台商品列表获取失败: {error_msg}")
            return {"success": False, "error": error_msg, "message": error_msg}

        # mtop 原始返回：res.data.data.itemSearchResponseList
        biz = ((response.get("res") or {}).get("data") or {}).get("data") or {}
        item_list = biz.get("itemSearchResponseList") or []

        items_list = [self._map_item(raw) for raw in item_list if isinstance(raw, dict)]
        has_more = bool(biz.get("hasNextPage"))

        logger.info(
            f"【{self.account_id}】卖家平台第 {page_number} 页获取到 {len(items_list)} 个商品，"
            f"hasNextPage={has_more}"
        )

        return {
            "success": True,
            "page_number": page_number,
            "page_size": page_size,
            "current_count": len(items_list),
            "items": items_list,
            "has_more": has_more,
            "raw_data": biz,
        }

    @staticmethod
    def _map_item(raw: dict) -> dict:
        """把卖家平台商品字段映射为与个人版一致的结构（供 save_fetched_items 复用）。"""
        item_id = str(raw.get("itemId") or "")
        price = str(raw.get("reservePrice") or "")
        image_url = str(raw.get("itemImageUrl") or "")
        return {
            "id": item_id,
            "title": raw.get("title", ""),
            "price": price,
            "price_text": price,
            "category_id": "",
            "auction_type": "",
            "item_status": raw.get("itemStatus", 0),
            "detail_url": "",
            "pic_info": {"url": image_url} if image_url else {},
            "detail_params": {},
            "track_params": {},
            "item_label_data": {},
            "card_type": 0,
            # 数据源标记：供入库/前端识别鱼小铺商品（改价等功能仅鱼小铺可用）
            "source": "seller",
            # 卖家平台特有信息：尽量多存储，便于界面展示与排查
            "item_status_desc": raw.get("itemStatusDesc", ""),
            "quantity": raw.get("quantity", ""),
            "gmt_create": raw.get("gmtCreate", ""),
            "gmt_shelf": raw.get("gmtShelf", ""),
            "item_type": raw.get("itemType", ""),
            "image_url": image_url,
            "fan_price": raw.get("fanPrice", {}),
            "item_extend_list": raw.get("itemExtendList", []),
            "item_operation_info": raw.get("itemOperationInfo", {}),
            # 多规格明细：每个 SKU 的规格名/值、单规格价格与库存（单规格商品为空列表）
            "idle_item_sku_list": SellerItemInfoManager._map_sku_list(
                raw.get("idleItemSkuList")
            ),
        }

    @staticmethod
    def _map_sku_list(raw_list: Any) -> list:
        """把卖家平台多规格明细 idleItemSkuList 映射为界面友好的规格结构。

        Args:
            raw_list: 卖家平台返回的 idleItemSkuList（单规格商品无此字段）。
        Returns:
            list[dict]：每项含 sku_id / inventory_id / quantity / price(元) / specs。
            specs 为 [{"name": 规格名, "value": 规格值}, ...]。
        """
        result: list = []
        if not isinstance(raw_list, list):
            return result
        for sku in raw_list:
            if not isinstance(sku, dict):
                continue
            features = sku.get("features") or {}
            # 价格优先取 features.priceYuan（元），否则用 priceInCent/price（分）换算
            price = str(features.get("priceYuan") or "").strip()
            if not price:
                cent = sku.get("priceInCent")
                if cent in (None, ""):
                    cent = sku.get("price")
                try:
                    price = f"{int(cent) / 100:.2f}" if cent not in (None, "") else ""
                except (ValueError, TypeError):
                    price = ""
            specs = [
                {
                    "name": str(prop.get("propertyText") or ""),
                    "value": str(prop.get("valueText") or ""),
                }
                for prop in (sku.get("propertyList") or [])
                if isinstance(prop, dict)
            ]
            result.append(
                {
                    "sku_id": str(sku.get("skuId") or ""),
                    "inventory_id": str(sku.get("inventoryId") or ""),
                    "quantity": sku.get("quantity", ""),
                    "price": price,
                    "specs": specs,
                }
            )
        return result

    async def close(self) -> None:
        """兼容 ItemInfoManager.close()；mtop_call 无常驻会话，无需清理。"""
        return None


def _parse_update_response(response: dict, account_id: str) -> dict:
    """解析卖家平台改价接口返回，统一为 {success, message}。

    成功返回结构：res.data.code == "success" 且 res.data.data == True，如
    {"data": {"code": "success", "data": true, "msg": "成功"}, "ret": ["SUCCESS::调用成功"]}。
    业务失败同样在 res.data.code/res.data.msg 表达（如 SKU_PRICE_ILLEGAL），
    此时 ret 仍可能是 SUCCESS，故必须以 res.data.code 判定结果。
    """
    if not response.get("success"):
        error_msg = response.get("error") or "改价请求失败"
        raw = json.dumps(response.get("res"), ensure_ascii=False)
        logger.error(f"【{account_id}】卖家平台改价失败: {error_msg}；完整返回: {raw}")
        return {"success": False, "message": error_msg}

    res = response.get("res") or {}
    # 业务结果在 res.data（其内 data 字段为布尔成功标记，勿再下探一层）
    inner = res.get("data")
    if not isinstance(inner, dict):
        inner = {}
    code = str(inner.get("code") or "").lower()
    ok = code == "success" or inner.get("data") is True
    if ok:
        logger.info(f"【{account_id}】卖家平台改价成功")
        return {"success": True, "message": "改价成功"}

    # 未识别为成功：把接口原始返回完整打印，便于排查真实拒绝原因
    raw = json.dumps(res, ensure_ascii=False)
    msg = str(inner.get("msg") or "").strip() or "卖家平台未接受本次改价"
    logger.warning(f"【{account_id}】卖家平台改价被拒绝: {msg}；完整返回: {raw}")
    return {"success": False, "message": msg}


async def update_seller_item_price(
    *,
    account_id: str,
    cookie: str,
    item_id: str,
    single: Optional[Dict[str, int]] = None,
    sku_list: Optional[List[Dict[str, Any]]] = None,
    owner_id: Optional[int] = None,
) -> dict:
    """调用卖家平台商品信息更新接口改价/改库存（单规格与多规格共用）。

    价格单位为「元」（平台内部再换算存为分）；接口要求价格与库存一并提交。
    抓包验证：提交 price=111111 后商品 priceYuan 变为 111111.00 元，故 price 字段即为元。

    Args:
        account_id: 闲鱼账号标识。
        cookie: 账号 Cookie 字符串。
        item_id: 商品ID。
        single: 单规格改价 {"price": 元(数值), "quantity": int}。
        sku_list: 多规格改价 [{"sku_id": str, "price": 元(数值), "quantity": int}, ...]。
        owner_id: 账号所属用户ID，令牌刷新回写使用。
    Returns:
        dict: {success, message}
    """
    if bool(single) == bool(sku_list):
        return {"success": False, "message": "改价参数错误：单规格与多规格需二选一"}

    data: Dict[str, Any] = {"itemId": str(item_id)}
    if single:
        # 单规格：顶层携带 price(元) 与 quantity
        data["quantity"] = int(single["quantity"])
        data["price"] = single["price"]
    else:
        # 多规格：itemSkuListStr 为 JSON 字符串，逐个 SKU 提交 skuId/quantity/price(元)
        sku_payload = [
            {
                "skuId": int(sku["sku_id"]),
                "quantity": int(sku["quantity"]),
                "price": sku["price"],
            }
            for sku in (sku_list or [])
        ]
        data["itemSkuListStr"] = json.dumps(sku_payload, ensure_ascii=False)

    # 打印实际提交的改价参数（不含 Cookie），便于与服务端返回对照排查
    logger.info(f"【{account_id}】卖家平台改价请求参数: {json.dumps(data, ensure_ascii=False)}")

    response = await mtop_call(
        account_id=account_id,
        cookies_str=cookie,
        api=SELLER_ITEM_UPDATE_API,
        version=SELLER_ITEM_UPDATE_VERSION,
        data=data,
        owner_id=owner_id,
        extra_params={
            "needLoginPC": "true",
            "accountSite": "xianyu",
        },
        extra_headers=SELLER_BIZ_HEADERS,
        origin=SELLER_ORIGIN,
        referer=SELLER_REFERER,
    )
    return _parse_update_response(response, account_id)


__all__ = ["SellerItemInfoManager", "update_seller_item_price"]
