"""
闲鱼商品详情客户端

功能：
1. 使用账号 Cookie 调用闲鱼网页版商品详情接口 mtop.taobao.idle.pc.detail
2. 复用 xianyu_utils 的签名与 Cookie 解析（仅需 sign + cookie）
3. 解析卖家真实用户ID（sellerDO.sellerId）与卖家昵称，返回完整详情数据

返回结构区分三种情况：
- success=True：成功，含 seller_user_id / seller_nick / detail
- account_invalid=True：账号 Cookie 不可用（Session/Token 过期、需登录、风控等），调用方应停用该账号
- 其余：商品级失败（商品下架/不存在等），不影响账号
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

import aiohttp
from loguru import logger

from common.utils.xianyu_utils import generate_sign, trans_cookies

DETAIL_API = "mtop.taobao.idle.pc.detail"
DETAIL_URL = f"https://h5api.m.goofish.com/h5/{DETAIL_API}/1.0/"

# 表示"账号 Cookie 不可用"的返回标志（命中则应停用该账号）
_ACCOUNT_INVALID_MARKERS = (
    "FAIL_SYS_SESSION_EXPIRED",
    "FAIL_SYS_TOKEN_EXOIRED",
    "FAIL_SYS_TOKEN_EXPIRED",
    "FAIL_SYS_TOKEN_EMPTY",
    "FAIL_SYS_ILLEGAL_ACCESS",
    "FAIL_SYS_USER_VALIDATE",
    "RGV587",
    "未登录",
    "登录",
    "会话失效",
)


class XianyuItemDetailClient:
    """闲鱼商品详情客户端（单账号）"""

    def __init__(self, cookie_id: str, cookies_str: str):
        self.cookie_id = cookie_id
        self.cookies_str = cookies_str

    async def get_detail(self, item_id: str, retry_count: int = 0) -> Dict[str, Any]:
        """调用商品详情接口。

        Returns:
            {
              success: bool,
              account_invalid: bool,   # True 表示该账号Cookie不可用，应停用
              seller_user_id: str|None,
              seller_nick: str|None,
              detail: dict|None,       # 详情接口返回的 data
              error: str,
            }
        """
        if retry_count >= 3:
            return {"success": False, "account_invalid": False, "seller_user_id": None,
                    "seller_nick": None, "detail": None, "error": "详情获取失败，重试次数过多"}

        data = {"itemId": str(item_id)}
        try:
            cookies = trans_cookies(self.cookies_str)
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "account_invalid": True, "seller_user_id": None,
                    "seller_nick": None, "detail": None, "error": f"Cookie解析失败: {exc}"}

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
            "api": DETAIL_API,
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.item.0.0",
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
                async with session.post(DETAIL_URL, params=params, data={"data": data_val}, headers=headers) as resp:
                    res_json = await resp.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"【{self.cookie_id}】详情接口请求异常: {exc}")
            await asyncio.sleep(0.5)
            return await self.get_detail(item_id, retry_count + 1)

        ret = res_json.get("ret") or [""]
        ret_msg = ret[0] if ret else ""

        if "SUCCESS::" in ret_msg:
            detail = res_json.get("data", {}) or {}
            seller = detail.get("sellerDO") or {}
            seller_user_id = seller.get("sellerId")
            seller_nick = seller.get("nick")
            return {
                "success": True,
                "account_invalid": False,
                "seller_user_id": str(seller_user_id) if seller_user_id is not None else None,
                "seller_nick": str(seller_nick) if seller_nick is not None else None,
                "detail": detail,
                "error": "",
            }

        # token 失效：刷新重试（同一账号再试一次）
        if "FAIL_SYS_TOKEN_EXOIRED" in ret_msg or "FAIL_SYS_TOKEN_EXPIRED" in ret_msg:
            await asyncio.sleep(0.5)
            return await self.get_detail(item_id, retry_count + 1)

        account_invalid = any(marker in ret_msg for marker in _ACCOUNT_INVALID_MARKERS)
        return {
            "success": False,
            "account_invalid": account_invalid,
            "seller_user_id": None,
            "seller_nick": None,
            "detail": None,
            "error": ret_msg or "详情获取失败",
        }


__all__ = ["XianyuItemDetailClient"]
