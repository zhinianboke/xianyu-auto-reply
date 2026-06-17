"""
闲鱼商品详情客户端

功能：
1. 使用账号 Cookie 调用闲鱼网页版商品详情接口 mtop.taobao.idle.pc.detail
2. 通过统一的 mtop 调用模块处理令牌过期刷新、Session过期/风控切换账号
3. 解析卖家真实用户ID（sellerDO.sellerId）与卖家昵称，返回完整详情数据

返回结构区分四种情况：
- success=True：成功，含 seller_user_id / seller_nick / detail
- account_invalid=True：账号不可用（Session过期/验证/挤爆），调用方应切换账号
- item_invalid=True：商品级明确失败（下架/不存在/跨境等），应停止重试
- 其余：临时失败（网络异常/重试耗尽），可下次重试
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from common.services.xianyu_mtop import mtop_call

DETAIL_API = "mtop.taobao.idle.pc.detail"
DETAIL_VERSION = "1.0"


class XianyuItemDetailClient:
    """闲鱼商品详情客户端（单账号）"""

    def __init__(self, cookie_id: str, cookies_str: str, owner_id: Optional[int] = None, proxy: Optional[str] = None):
        self.cookie_id = cookie_id
        self.cookies_str = cookies_str
        self.owner_id = owner_id
        self.proxy = proxy

    async def get_detail(self, item_id: str) -> Dict[str, Any]:
        """调用商品详情接口。

        Returns:
            {
              success: bool,
              account_invalid: bool,   # True 表示账号不可用，应切换账号
              item_invalid: bool,      # True 表示商品级明确失败，应停止重试
              seller_user_id: str|None,
              seller_nick: str|None,
              detail: dict|None,       # 详情接口返回的 data
              error: str,
            }
        """
        result = await mtop_call(
            self.cookie_id, self.cookies_str, DETAIL_API, DETAIL_VERSION, {"itemId": str(item_id)},
            owner_id=self.owner_id,
            extra_params={"spm_cnt": "a21ybx.item.0.0"},
        )
        # 令牌刷新后回写实例 Cookie
        self.cookies_str = result.get("cookies_str", self.cookies_str)

        if result.get("success"):
            detail = (result.get("res") or {}).get("data", {}) or {}
            seller = detail.get("sellerDO") or {}
            seller_user_id = seller.get("sellerId")
            seller_nick = seller.get("nick")
            return {
                "success": True,
                "account_invalid": False,
                "item_invalid": False,
                "seller_user_id": str(seller_user_id) if seller_user_id is not None else None,
                "seller_nick": str(seller_nick) if seller_nick is not None else None,
                "detail": detail,
                "error": "",
            }

        account_invalid = bool(result.get("account_invalid"))
        # 拿到了服务端业务失败响应且非账号问题 -> 商品级明确失败（下架/不存在/跨境等），停止重试；
        # 网络异常/重试耗尽（res 为 None）视为临时失败，可下次重试
        item_invalid = (not account_invalid) and (result.get("res") is not None)
        return {
            "success": False,
            "account_invalid": account_invalid,
            "item_invalid": item_invalid,
            "seller_user_id": None,
            "seller_nick": None,
            "detail": None,
            "error": result.get("error") or "详情获取失败",
        }


__all__ = ["XianyuItemDetailClient"]
