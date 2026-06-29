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

import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger

from common.services.xianyu_mtop import mtop_call

SEARCH_API = "mtop.taobao.idlemtopsearch.pc.search"
SEARCH_VERSION = "1.0"


class XianyuSearchClient:
    """闲鱼商品搜索客户端（单账号）"""

    def __init__(self, cookie_id: str, cookies_str: str, owner_id: Optional[int] = None, proxy: Optional[str] = None):
        self.cookie_id = cookie_id
        self.cookies_str = cookies_str
        self.owner_id = owner_id
        self.proxy = proxy

    def _build_search_filter(
        self,
        price_min: Optional[float],
        price_max: Optional[float],
        publish_days: Optional[int] = None,
    ) -> str:
        """构造 searchFilter（个人闲置 + 上新天数 + 价格区间），多个条件以分号拼接。"""
        # 固定只采集个人卖家闲置（quickFilter:filterPersonal;）
        parts: List[str] = ["quickFilter:filterPersonal;"]
        # 上新天数筛选：publishDays:N;
        if publish_days:
            try:
                days = int(publish_days)
                if days > 0:
                    parts.append(f"publishDays:{days};")
            except (TypeError, ValueError):
                pass
        # 价格区间筛选：priceRange:lo,hi;
        if price_min is not None or price_max is not None:
            lo = "" if price_min is None else (str(int(price_min)) if float(price_min).is_integer() else str(price_min))
            hi = "undefined" if price_max is None else (str(int(price_max)) if float(price_max).is_integer() else str(price_max))
            parts.append(f"priceRange:{lo},{hi};")
        return "".join(parts)

    async def search(
        self,
        keyword: str,
        page_number: int = 1,
        sort_field: str = "",
        sort_value: str = "",
        rows_per_page: int = 30,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        publish_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """调用搜索接口（令牌过期自动刷新重试、Session/风控切换账号）。

        Returns:
            {success: bool, items: list(resultList原始项), has_next_page: bool,
             account_invalid: bool, error: str}
        """
        search_filter = self._build_search_filter(price_min, price_max, publish_days)
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

        result = await mtop_call(
            self.cookie_id, self.cookies_str, SEARCH_API, SEARCH_VERSION, data,
            owner_id=self.owner_id,
            extra_params={"spm_cnt": "a21ybx.search.0.0", "spm_pre": "a21ybx.home.searchInput.0"},
            proxy=self.proxy,
        )
        # 令牌刷新后回写实例 Cookie
        self.cookies_str = result.get("cookies_str", self.cookies_str)

        res_json = result.get("res")
        if res_json is not None:
            # 打印搜索接口完整返回结果（便于排查风控/验证等问题）
            logger.info(
                f"【{self.cookie_id}】搜索接口返回（关键字={keyword}，第{page_number}页）: "
                f"{json.dumps(res_json, ensure_ascii=False)}"
            )

        if result.get("success"):
            data_node = (res_json or {}).get("data", {}) or {}
            result_list = data_node.get("resultList", []) or []
            result_info = data_node.get("resultInfo", {}) or {}
            has_next = bool(result_info.get("hasNextPage"))
            return {"success": True, "items": result_list, "has_next_page": has_next,
                    "account_invalid": False, "error": ""}

        return {
            "success": False, "items": [], "has_next_page": False,
            "account_invalid": bool(result.get("account_invalid")),
            "error": result.get("error") or "搜索失败",
        }


def extract_seller_user_id_from_pic(pic_url: Optional[str]) -> Optional[str]:
    """从商品主图 picUrl 中提取卖家真实数字用户ID。

    闲鱼/淘宝图片 CDN 约定：卖家上传的商品主图(xy_item)路径形如
    /bao/uploaded/i{N}/{sellerUserId}/O1CN...，其中 {sellerUserId} 即上传者
    （卖家）的真实数字用户ID。平台图(fleamarket)等无该路径段，返回 None。

    提取到的真实ID用于在采集入库阶段直接补全 seller_user_id，约 85% 的商品可
    零成本补全，无需再经 seller_fill 定时任务调用商品详情接口。

    Args:
        pic_url: 商品主图 URL

    Returns:
        卖家真实数字用户ID；无法提取时返回 None（交由 seller_fill 兜底补全）
    """
    if not pic_url:
        return None
    matched = re.search(r"/bao/uploaded/i\d+/(\d+)/O1CN", str(pic_url))
    return matched.group(1) if matched else None


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
    seller_avatar = ex_content.get("userAvatarUrl")
    publish_time = click_args.get("publishTime")
    target_url = main.get("targetUrl")

    # 营销标签与真实想要数：搜索结果的 wantNum 恒为 0 不可靠，
    # 真实想要数与"X天内上新/降价"等标签藏在 clickParam.args.serviceUtParams 的 content 中。
    tags: List[str] = []
    want_count: Optional[str] = None
    service_ut = click_args.get("serviceUtParams")
    if service_ut:
        try:
            ut_list = json.loads(service_ut) if isinstance(service_ut, str) else service_ut
        except (ValueError, TypeError):
            ut_list = None
        for ut in ut_list or []:
            content = ((ut or {}).get("args") or {}).get("content")
            if not content:
                continue
            content = str(content).strip()
            if content and content not in tags:
                tags.append(content)
            # 从"235人想要"中提取真实想要数
            if want_count is None:
                matched = re.search(r"(\d+)\s*人?想要", content)
                if matched:
                    want_count = matched.group(1)
    # 标签兜底：部分商品想要数也可能在 fishTags 文本中，这里仅以 serviceUtParams 为准
    tags_text = ",".join(tags) if tags else None

    return {
        "item_id": item_id,
        "title": str(title) if title is not None else None,
        "price": str(price) if price is not None else None,
        "area": str(area) if area is not None else None,
        "pic_url": str(pic_url) if pic_url is not None else None,
        "seller_id": str(seller_id) if seller_id is not None else None,
        # 卖家真实数字用户ID：直接从主图 picUrl 路径提取（取不到则为 None，由 seller_fill 兜底）
        "seller_user_id": extract_seller_user_id_from_pic(pic_url),
        "seller_nick": str(seller_nick) if seller_nick is not None else None,
        "seller_avatar": str(seller_avatar) if seller_avatar is not None else None,
        "want_count": want_count,
        "tags": tags_text,
        "publish_time_ms": str(publish_time) if publish_time is not None else None,
        "target_url": str(target_url) if target_url is not None else None,
        "raw_main": main,
    }


__all__ = ["XianyuSearchClient", "parse_search_item", "extract_seller_user_id_from_pic"]
