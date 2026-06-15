"""
闲鱼商品搜索客户端

功能：
1. 使用账号 Cookie 调用闲鱼网页版商品搜索接口 mtop.taobao.idlemtopsearch.pc.search
2. 复用 xianyu_utils 的签名与 Cookie 解析（仅需 sign + cookie，无需风控参数 bx-ua）
3. 支持按排序字段（上新/降价）与价格区间筛选搜索

说明：
- 经实测，该搜索接口在仅携带 sign + 登录 Cookie 的情况下即可正常返回，无需 bx-ua/bx-umidtoken。
- token 失效（FAIL_SYS_TOKEN_EXOIRED）时自动重试。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

from common.utils.xianyu_utils import generate_sign, trans_cookies

SEARCH_API = "mtop.taobao.idlemtopsearch.pc.search"
SEARCH_URL = f"https://h5api.m.goofish.com/h5/{SEARCH_API}/1.0/"


class XianyuSearchClient:
    """闲鱼商品搜索客户端（单账号）"""

    def __init__(self, cookie_id: str, cookies_str: str):
        self.cookie_id = cookie_id
        self.cookies_str = cookies_str

    def _build_search_filter(
        self,
        price_min: Optional[float],
        price_max: Optional[float],
    ) -> str:
        """构造价格区间筛选条件 searchFilter。"""
        if price_min is None and price_max is None:
            return ""
        lo = "" if price_min is None else (str(int(price_min)) if float(price_min).is_integer() else str(price_min))
        hi = "undefined" if price_max is None else (str(int(price_max)) if float(price_max).is_integer() else str(price_max))
        return f"priceRange:{lo},{hi};"

    async def search(
        self,
        keyword: str,
        page_number: int = 1,
        sort_field: str = "",
        sort_value: str = "",
        rows_per_page: int = 30,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """调用搜索接口。

        Returns:
            {success: bool, items: list(resultList原始项), has_next_page: bool, error: str}
        """
        if retry_count >= 3:
            return {"success": False, "items": [], "has_next_page": False, "error": "搜索失败，重试次数过多"}

        search_filter = self._build_search_filter(price_min, price_max)
        data = {
            "pageNumber": page_number,
            "keyword": keyword,
            "fromFilter": bool(sort_field or search_filter),
            "rowsPerPage": rows_per_page,
            "sortValue": sort_value or "",
            "sortField": sort_field or "",
            "customDistance": "",
            "gps": "",
            "propValueStr": {"searchFilter": search_filter},
            "customGps": "",
            "searchReqFromPage": "pcSearch",
            "extraFilterValue": "{}",
            "userPositionJson": "{}",
        }

        try:
            cookies = trans_cookies(self.cookies_str)
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "items": [], "has_next_page": False, "error": f"Cookie解析失败: {exc}"}

        token = cookies.get("_m_h5_tk", "").split("_")[0] if cookies.get("_m_h5_tk") else ""
        t = str(int(time.time()) * 1000)
        data_val = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        sign = generate_sign(t, token, data_val)

        params = {
            "jsv": "2.7.2",
            "appKey": "34839810",
            "t": t,
            "sign": sign,
            "v": "1.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": SEARCH_API,
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.search.0.0",
            "spm_pre": "a21ybx.home.searchInput.0",
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.goofish.com",
            "Referer": "https://www.goofish.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Cookie": self.cookies_str,
        }

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(SEARCH_URL, params=params, data={"data": data_val}, headers=headers) as resp:
                    res_json = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"【{self.cookie_id}】搜索接口请求异常: {exc}")
            await asyncio.sleep(0.5)
            return await self.search(keyword, page_number, sort_field, sort_value, rows_per_page, price_min, price_max, retry_count + 1)

        ret = res_json.get("ret") or [""]
        ret_msg = ret[0] if ret else ""
        if "SUCCESS::" in ret_msg:
            data_node = res_json.get("data", {}) or {}
            result_list = data_node.get("resultList", []) or []
            result_info = data_node.get("resultInfo", {}) or {}
            has_next = bool(result_info.get("hasNextPage"))
            return {"success": True, "items": result_list, "has_next_page": has_next, "error": ""}

        if "FAIL_SYS_TOKEN_EXOIRED" in ret_msg or "令牌" in ret_msg or "token" in ret_msg.lower():
            logger.warning(f"【{self.cookie_id}】搜索token失效，重试: {ret_msg}")
            await asyncio.sleep(0.5)
            return await self.search(keyword, page_number, sort_field, sort_value, rows_per_page, price_min, price_max, retry_count + 1)

        return {"success": False, "items": [], "has_next_page": False, "error": ret_msg or "搜索失败"}


def parse_search_item(result_entry: dict) -> Optional[Dict[str, Any]]:
    """从搜索结果单项中解析出商品关键信息。

    Args:
        result_entry: data.resultList 中的单个元素

    Returns:
        商品信息字典（含 item_id 等）；无法解析出 item_id 时返回 None
    """
    try:
        main = (((result_entry or {}).get("data") or {}).get("item") or {}).get("main") or {}
    except Exception:  # noqa: BLE001
        return None
    if not main:
        return None

    ex_content = main.get("exContent") or {}
    click_args = ((main.get("clickParam") or {}).get("args")) or {}

    item_id = str(ex_content.get("itemId") or click_args.get("item_id") or click_args.get("id") or "").strip()
    if not item_id:
        return None

    title = ex_content.get("title") or (ex_content.get("detailParams") or {}).get("title")
    # 价格：优先取 clickParam.args 里的纯数字价格，其次 detailParams.soldPrice，
    # 最后兜底解析 exContent.price 富文本数组（[{text:'¥'},{text:'8500'}]）
    price = click_args.get("price") or click_args.get("displayPrice")
    if not price:
        price = (ex_content.get("detailParams") or {}).get("soldPrice")
    if not price:
        raw_price = ex_content.get("price")
        if isinstance(raw_price, list):
            price = "".join(
                str(seg.get("text", ""))
                for seg in raw_price
                if isinstance(seg, dict) and seg.get("type") in ("integer", "decimal")
            )
        elif isinstance(raw_price, (str, int, float)):
            price = str(raw_price)
    area = ex_content.get("area")
    pic_url = ex_content.get("picUrl")
    seller_nick = ex_content.get("userNickName") or (ex_content.get("detailParams") or {}).get("userNick")
    seller_id = click_args.get("seller_id")
    want_count = click_args.get("wantNum")
    publish_time = click_args.get("publishTime")
    target_url = main.get("targetUrl")

    return {
        "item_id": item_id,
        "title": str(title) if title is not None else None,
        "price": str(price) if price is not None else None,
        "area": str(area) if area is not None else None,
        "pic_url": str(pic_url) if pic_url is not None else None,
        "seller_id": str(seller_id) if seller_id is not None else None,
        "seller_nick": str(seller_nick) if seller_nick is not None else None,
        "want_count": str(want_count) if want_count is not None else None,
        "publish_time_ms": str(publish_time) if publish_time is not None else None,
        "target_url": str(target_url) if target_url is not None else None,
        "raw_main": main,
    }


__all__ = ["XianyuSearchClient", "parse_search_item"]
