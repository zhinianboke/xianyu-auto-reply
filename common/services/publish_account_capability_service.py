"""
闲鱼发布账号能力检测服务。

功能：
1. 优先调用鱼小铺卖家后台的发布初始化接口识别账号是否开通鱼小铺；
2. 后台接口不可用（普通卖家没有卖家后台）时回落个人版发布页接口判定；
3. 返回多规格能力和服务费配置，供前端展示与后端发布分流使用；
4. 用 detection_reliable 标记回落判定是否可信，发布链路据此拒绝按个人版发布。

说明：
- 抓包确认鱼小铺卖家后台用的是 mtop.idle.pc.backend.idleitem.preget
  （Origin/Referer 为 seller.goofish.com、带 idle_site_biz_code=COMMONPRO），
  返回的服务费规则是 fish-shop-service-fee-rule；
- 只用个人版 mtop.idle.pc.idleitem.preget 判定时，鱼小铺账号在个人版发布页拿到的
  可能是个人卖家的服务费文案，会被误判成普通卖家而让发布退回个人版接口，因此后台接口优先。
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from common.services.xianyu_mtop import VALIDATE_MARKERS, mtop_call
from common.utils.cookie_refresh import is_session_expired_error


# 个人版网页发布页初始化接口
PREGET_API = "mtop.idle.pc.idleitem.preget"
PUBLISH_ORIGIN = "https://www.goofish.com"
PUBLISH_REFERER = "https://www.goofish.com/publish"
# 鱼小铺卖家后台发布初始化接口（抓包确认，与商品发布/编辑同一套站点标识）
BACKEND_PREGET_API = "mtop.idle.pc.backend.idleitem.preget"
BACKEND_PREGET_DATA = {"publishScene": "pcBackendPublish"}
SELLER_ORIGIN = "https://seller.goofish.com"
SELLER_REFERER = "https://seller.goofish.com/?site=COMMONPRO"
SELLER_EXTRA_PARAMS = {
    "idle_site_biz_code": "COMMONPRO",
    "spm_cnt": "a21107h.42826273.0.0",
}
SELLER_EXTRA_HEADERS = {
    "idle_site_biz_code": "COMMONPRO",
    "idle_user_group_member_id": "",
}

# 鱼小铺后台接口失败时，下列错误标志说明「失败原因与账号是否开通鱼小铺无关」，
# 因此回落个人版发布页得出的「普通卖家」结论不可信：
# - FAIL_SYS_*：mtop 系统级失败（限流 FAIL_SYS_FLOW_LIMITED、服务不可用、非法访问、令牌问题等）
# - VALIDATE_MARKERS：风控/验证/机器检测类标志，直接复用 mtop 的判定元组，避免两处维护漂移
# 只有闲鱼以业务原因（非以下标志）拒绝访问卖家后台，才能证明该账号确实没有鱼小铺后台。
_UNTRUSTED_FAILURE_MARKERS = ("FAIL_SYS_",) + VALIDATE_MARKERS


def _fallback_trust(backend: dict[str, Any]) -> tuple[bool, str]:
    """判断鱼小铺后台接口失败后，回落个人版发布页的判定是否可信。

    鱼小铺账号一旦被误判成普通卖家，发布会走个人版接口，多规格和独立库存能力会丢失且
    商品已上架无法回滚，因此只在「闲鱼明确以业务原因拒绝该账号访问卖家后台」时才认可回落结论。

    判据取自响应里的原始 ret 首项而非 mtop_call 的 error 字段：error 在「响应体没有 ret」时
    会被 mtop_call 兜底成「调用失败」这类通用文案（见 common/services/xianyu_mtop.py 的业务失败分支），
    通用文案不含任何标志，若照它判断会把网关/WAF 返回的无结论响应当成「闲鱼明确拒绝」。

    Args:
        backend: 鱼小铺后台 preget 的 mtop 返回。
    Returns:
        tuple: (回落判定是否可信, 不可信原因)；可信时原因为空字符串。
    """
    if backend.get("success"):
        # 后台接口能调通却读不出发布配置：普通卖家本不该调通，这种账号更可能是鱼小铺
        return False, "鱼小铺后台返回了无法识别的发布配置"
    res = backend.get("res")
    if not isinstance(res, dict):
        # 网络异常、超时、令牌刷新重试耗尽，闲鱼没有给出任何结论
        return False, f"鱼小铺后台接口未返回结果（{backend.get('error') or '网络异常或重试次数耗尽'}）"
    ret = res.get("ret")
    ret_msg = str(ret[0]).strip() if isinstance(ret, list) and ret else ""
    if not ret_msg:
        # 响应是合法 JSON 但没有 ret（网关/WAF 拦截、代理层错误体），闲鱼未给出业务结论
        return False, "鱼小铺后台接口未返回错误码（响应中缺少 ret）"
    if any(marker in ret_msg for marker in _UNTRUSTED_FAILURE_MARKERS):
        return False, f"鱼小铺后台接口系统级失败（{ret_msg}）"
    return True, ""


def _parse_capability(raw_data: dict[str, Any]) -> tuple[bool | None, dict[str, Any], Any, bool]:
    """从 preget 返回的配置里判定账号是否开通鱼小铺。

    Args:
        raw_data: preget 接口返回的 data 节点。
    Returns:
        tuple: (是否鱼小铺, 佣金配置, supportSkuOrInventory 原值, 判定是否来自服务费文案)；
            无法识别账号类型时第一项为 None，由调用方决定回落策略。
            最后一项为 False 表示结论只是靠 supportSkuOrInventory 反推（弱判定）：
            该字段在部分类目下可能为 false，不足以否定鱼小铺，调用方不应据此直接采信。
    """
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
        return True, commission, support_sku, True
    if has_personal_marker:
        return False, commission, support_sku, True
    if isinstance(support_sku, bool):
        return support_sku, commission, support_sku, False
    return None, commission, support_sku, False


class PublishAccountCapabilityService:
    """根据账号 Cookie 查询闲鱼发布能力。"""

    async def _call_preget(
        self,
        *,
        account_id: str,
        cookie: str,
        owner_id: int | None,
        seller_backend: bool,
    ) -> dict[str, Any]:
        """调用发布初始化接口。

        Args:
            account_id: 闲鱼账号标识。
            cookie: 账号 Cookie。
            owner_id: 账号所属用户 ID，用于令牌刷新后的 Cookie 回写。
            seller_backend: True 走鱼小铺卖家后台接口，False 走个人版发布页接口。
        Returns:
            dict: mtop_call 的原始返回。
        """
        if seller_backend:
            return await mtop_call(
                account_id=account_id,
                cookies_str=cookie,
                api=BACKEND_PREGET_API,
                version="1.0",
                data=BACKEND_PREGET_DATA,
                owner_id=owner_id,
                extra_params=SELLER_EXTRA_PARAMS,
                origin=SELLER_ORIGIN,
                referer=SELLER_REFERER,
                extra_headers=SELLER_EXTRA_HEADERS,
            )
        return await mtop_call(
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

    @staticmethod
    def _success_result(
        *,
        is_fish_shop: bool,
        commission: dict[str, Any],
        support_sku: Any,
        cookie: str,
        detection_reliable: bool,
        unreliable_reason: str = "",
    ) -> dict[str, Any]:
        """组装检测成功的返回结构。

        Args:
            is_fish_shop: 是否开通鱼小铺。
            commission: 佣金配置。
            support_sku: supportSkuOrInventory 原值。
            cookie: 最新 Cookie。
            detection_reliable: 判定是否可信；False 表示鱼小铺后台配置不可用导致
                「个人卖家」的结论可能是误判，发布链路必须据此拒绝发布。
            unreliable_reason: 判定不可信的具体原因，用于发布链路的错误提示与排查。
        Returns:
            dict: 与前端和发布分流约定一致的检测结果。
        """
        return {
            "success": True,
            "message": "账号发布能力检测成功",
            "account_invalid": False,
            "cookies_str": cookie,
            "is_fish_shop": is_fish_shop,
            "detection_reliable": detection_reliable,
            "detection_unreliable_reason": unreliable_reason,
            "support_sku_or_inventory": (
                bool(support_sku) if isinstance(support_sku, bool) else is_fish_shop
            ),
            "commission_config": {
                "title": str(commission.get("commissionTitle") or ""),
                "default_title": str(commission.get("defaultCommissionTitle") or ""),
                "tips": str(commission.get("commissionTips") or ""),
                "percent": str(commission.get("percent") or ""),
                "max_commission": str(commission.get("maxCommission") or ""),
                "tip_url": str(commission.get("tipUrl") or ""),
            },
        }

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
            包含账号类型、多规格能力、服务费配置和最新 Cookie 的检测结果；
            另含 detection_reliable 标志，False 表示「个人卖家」结论可能是误判。
        """
        # 1) 抓包确认鱼小铺发布走卖家后台接口，优先用它判定，避免鱼小铺账号被误判成个人版
        backend = await self._call_preget(
            account_id=account_id, cookie=cookie, owner_id=owner_id, seller_backend=True
        )
        latest_cookie = backend.get("cookies_str") or cookie
        backend_raw = (backend.get("res") or {}).get("data") if backend.get("success") else None
        if isinstance(backend_raw, dict):
            (
                backend_is_fish_shop,
                backend_commission,
                backend_support_sku,
                backend_from_marker,
            ) = _parse_capability(backend_raw)
            # 后台接口调通但读不到服务费文案、只能靠 supportSkuOrInventory 反推出「个人卖家」时不采信：
            # 该字段在部分类目下可能为 false，而普通卖家本不该调通卖家后台，这种账号更可能是鱼小铺。
            # 此时落到下面的回落分支，由 _fallback_trust 标记为不可信，发布链路据此拒绝发布。
            if backend_is_fish_shop is not None and (backend_from_marker or backend_is_fish_shop):
                return self._success_result(
                    is_fish_shop=backend_is_fish_shop,
                    commission=backend_commission,
                    support_sku=backend_support_sku,
                    cookie=latest_cookie,
                    detection_reliable=True,
                )
        if backend.get("account_invalid"):
            # 只有 Session 过期才是真的需要重新登录；普通卖家越权访问卖家后台会命中风控/
            # 非法访问标志，同样被 mtop_call 标成 account_invalid，若在此早退会让普通卖家
            # 收到「请重新登录」的误导提示并彻底失去发布能力，因此这类失败继续回落个人版判定。
            backend_ret = (backend.get("res") or {}).get("ret") if isinstance(backend.get("res"), dict) else None
            if is_session_expired_error(backend_ret or []):
                return {
                    "success": False,
                    "message": "账号发布能力检测失败：账号登录状态已失效，请重新登录",
                    "account_invalid": True,
                    "cookies_str": latest_cookie,
                }
        # 普通卖家没有鱼小铺卖家后台，后台接口调不通属预期情况，回落个人版发布页判定。
        # 但闲鱼限流、系统异常、风控、网络超时等失败与账号是否开通鱼小铺无关，这些形态下
        # 鱼小铺账号也会走到回落，而个人版发布页对鱼小铺账号可能返回个人卖家的服务费文案，
        # 从而被误判成普通卖家。这类情况标记为判定不可信，由发布链路拒绝发布；
        # 编辑与商品同步仍按回落结果处理（误判只会拒绝操作，不会把商品按个人版写到平台）。
        fallback_reliable, unreliable_reason = _fallback_trust(backend)
        logger.info(
            f"账号[{account_id}]鱼小铺后台发布配置不可用，回落个人版发布页判定账号类型"
            f"（判定可信={fallback_reliable}）: "
            f"{unreliable_reason or backend.get('error') or '后台接口明确拒绝该账号访问'}"
        )

        # 2) 个人版发布页接口判定
        response = await self._call_preget(
            account_id=account_id, cookie=latest_cookie, owner_id=owner_id, seller_backend=False
        )
        latest_cookie = response.get("cookies_str") or latest_cookie
        if not response.get("success"):
            # 与后台分支保持一致：Session 过期给「请重新登录」的明确指引，
            # 而不是把 FAIL_SYS_SESSION_EXPIRED 这类原始错误码直接抛给用户
            personal_ret = (response.get("res") or {}).get("ret") if isinstance(response.get("res"), dict) else None
            if is_session_expired_error(personal_ret):
                return {
                    "success": False,
                    "message": "账号发布能力检测失败：账号登录状态已失效，请重新登录",
                    "account_invalid": True,
                    "cookies_str": latest_cookie,
                }
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

        is_fish_shop, commission, support_sku, from_marker = _parse_capability(raw_data)
        if is_fish_shop is None:
            return {
                "success": False,
                "message": "账号发布能力检测失败：无法识别账号是否开通鱼小铺",
                "account_invalid": False,
                "cookies_str": latest_cookie,
            }
        # 判定为鱼小铺不存在「被当成个人卖家发布」的风险，无需怀疑；但仅靠 supportSkuOrInventory
        # 反推出的鱼小铺是弱判定（个人版发布页没给出任何服务费文案），如实标记为不可信。
        # 判定为个人卖家时，只有后台接口明确以业务原因拒绝访问才算可信。
        reliable = fallback_reliable or (is_fish_shop and from_marker)
        return self._success_result(
            is_fish_shop=is_fish_shop,
            commission=commission,
            support_sku=support_sku,
            cookie=latest_cookie,
            detection_reliable=reliable,
            unreliable_reason="" if reliable else unreliable_reason,
        )


__all__ = ["PublishAccountCapabilityService"]
