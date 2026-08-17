"""
闲鱼发布账号能力检测服务。

功能：
1. 调用网页发布初始化接口识别鱼小铺与普通卖家账号；
2. 返回多规格能力和服务费配置，供前端展示与后端发布分流使用。
"""
from __future__ import annotations

from typing import Any

from common.services.xianyu_mtop import mtop_call


PREGET_API = "mtop.idle.pc.idleitem.preget"
PUBLISH_ORIGIN = "https://www.goofish.com"
PUBLISH_REFERER = "https://www.goofish.com/publish"


class PublishAccountCapabilityService:
    """根据账号 Cookie 查询闲鱼发布能力。"""

    async def detect(
        self,
        *,
        account_id: str,
        cookie: str,
        owner_id: int | None,
    ) -> dict[str, Any]:
        """
        查询账号发布初始化配置。

        Args:
            account_id: 闲鱼账号标识。
            cookie: 账号 Cookie。
            owner_id: 账号所属用户 ID，用于令牌刷新后的 Cookie 回写。
        Returns:
            包含账号类型、多规格能力、服务费配置和最新 Cookie 的检测结果。
        """
        response = await mtop_call(
            account_id=account_id,
            cookies_str=cookie,
            api=PREGET_API,
            version="1.0",
            data={},
            owner_id=owner_id,
            extra_params={"spm_cnt": "a21ybx.publish.0.0"},
            origin=PUBLISH_ORIGIN,
            referer=PUBLISH_REFERER,
        )
        latest_cookie = response.get("cookies_str") or cookie
        if not response.get("success"):
            return {
                "success": False,
                "message": f"账号发布能力检测失败：{response.get('error') or '闲鱼接口调用失败'}",
                "account_invalid": bool(response.get("account_invalid")),
                "cookies_str": latest_cookie,
            }

        raw_data = (response.get("res") or {}).get("data")
        if not isinstance(raw_data, dict):
            return {
                "success": False,
                "message": "账号发布能力检测失败：闲鱼接口未返回发布配置",
                "account_invalid": False,
                "cookies_str": latest_cookie,
            }

        commission = raw_data.get("commissionConfig")
        commission = commission if isinstance(commission, dict) else {}
        support_sku = raw_data.get("supportSkuOrInventory")
        tip_url = str(commission.get("tipUrl") or "")
        commission_title = str(commission.get("defaultCommissionTitle") or "")

        has_shop_marker = (
            "fish-shop-service-fee-rule" in tip_url
            or "鱼小铺" in commission_title
            or "鱼小铺" in str(commission.get("commissionTitle") or "")
        )
        has_personal_marker = (
            "fish-seller-service-fee-rule" in tip_url
            or commission_title == "基础软件服务费"
        )
        if has_shop_marker:
            is_fish_shop = True
        elif has_personal_marker:
            is_fish_shop = False
        elif isinstance(support_sku, bool):
            is_fish_shop = support_sku
        else:
            return {
                "success": False,
                "message": "账号发布能力检测失败：无法识别账号是否开通鱼小铺",
                "account_invalid": False,
                "cookies_str": latest_cookie,
            }

        return {
            "success": True,
            "message": "账号发布能力检测成功",
            "account_invalid": False,
            "cookies_str": latest_cookie,
            "is_fish_shop": is_fish_shop,
            "support_sku_or_inventory": bool(support_sku) if isinstance(support_sku, bool) else is_fish_shop,
            "commission_config": {
                "title": str(commission.get("commissionTitle") or ""),
                "default_title": commission_title,
                "tips": str(commission.get("commissionTips") or ""),
                "percent": str(commission.get("percent") or ""),
                "max_commission": str(commission.get("maxCommission") or ""),
                "tip_url": tip_url,
            },
        }


__all__ = ["PublishAccountCapabilityService"]
