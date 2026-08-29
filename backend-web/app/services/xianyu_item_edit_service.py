"""
闲鱼卖家后台（鱼小铺）商品编辑服务。

功能：
1. 调用 mtop.idle.pc.backend.idleitem.editdetail 拉取平台商品详情，转成编辑表单数据；
2. 调用 mtop.idle.pc.backend.idleitem.edit 提交编辑，载荷与单品发布完全共用一套构造器；
3. 提交前重新拉取平台详情作为快照，未改动的图片/视频/地址/运费直接复用，避免全量覆盖丢字段。

说明：
- 两个接口的请求头、spm 参数与单品发布接口一致（抓包确认）；
- edit 为全量覆盖式提交，不是增量更新，因此必须带上完整载荷；
- 价格单位为分（priceInCent），与已有改价接口（元）不同，切勿混用；
- 仅鱼小铺账号可用，非鱼小铺账号返回业务失败而不抛异常。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.paths import STATIC_ROOT
from app.services.xianyu_direct_payload import DirectPublishError, text as _text
from app.services.xianyu_item_edit_mapper import map_edit_detail_to_form
from app.services.xianyu_item_payload_builder import build_item_payload
from common.services.xianyu_mtop import mtop_call
from common.services.xianyu_publish_service import detect_publish_account_capability

EDIT_DETAIL_API = "mtop.idle.pc.backend.idleitem.editdetail"
EDIT_API = "mtop.idle.pc.backend.idleitem.edit"
SELLER_ORIGIN = "https://seller.goofish.com"
SELLER_REFERER = "https://seller.goofish.com/?site=COMMONPRO"
# 抓包确认：编辑接口与发布接口使用同一套 spm 与站点标识
SELLER_EXTRA_PARAMS = {
    "idle_site_biz_code": "COMMONPRO",
    "spm_cnt": "a21107h.42826273.0.0",
}
SELLER_EXTRA_HEADERS = {
    "idle_site_biz_code": "COMMONPRO",
    "idle_user_group_member_id": "",
}
# 业务失败码白名单：平台成功时可能返回这些值，其余非空取值一律视为失败
_SUCCESS_CODES = {"", "0", "200", "success", "SUCCESS"}


def _fail(message: str, *, account_invalid: bool, cookie: str) -> dict[str, Any]:
    """构造统一的失败返回，避免各分支重复拼字典。"""
    return {
        "success": False,
        "message": message,
        "account_invalid": account_invalid,
        "cookies_str": cookie,
        "data": None,
    }


async def _call_seller_api(
    *, account_id: str, cookie: str, owner_id: int | None, api: str, data: dict[str, Any]
) -> dict[str, Any]:
    """按卖家后台的请求头与 spm 参数调用编辑相关 mtop 接口。

    Args:
        account_id: 闲鱼账号标识。
        cookie: 账号 Cookie。
        owner_id: 账号所属用户ID，令牌刷新回写使用。
        api: mtop 接口名。
        data: 接口业务参数。
    Returns:
        dict: mtop_call 的原始返回（success/account_invalid/res/error/cookies_str）。
    """
    return await mtop_call(
        account_id=account_id,
        cookies_str=cookie,
        api=api,
        version="1.0",
        data=data,
        owner_id=owner_id,
        extra_params=SELLER_EXTRA_PARAMS,
        origin=SELLER_ORIGIN,
        referer=SELLER_REFERER,
        extra_headers=SELLER_EXTRA_HEADERS,
    )


def _loggable_response(response: dict[str, Any]) -> str:
    """把 mtop 返回裁剪成可写日志的内容（剔除 Cookie 等凭据）。

    Args:
        response: mtop_call 的原始返回。
    Returns:
        str: 仅含业务字段（success/account_invalid/res/error）的 JSON 字符串。
    """
    safe = {key: response.get(key) for key in ("success", "account_invalid", "res", "error")}
    return json.dumps(safe, ensure_ascii=False, default=str)


async def _ensure_fish_shop(
    *, account_id: str, cookie: str, owner_id: int | None
) -> tuple[str, dict[str, Any] | None]:
    """校验账号已开通鱼小铺。

    Args:
        account_id: 闲鱼账号标识。
        cookie: 账号 Cookie。
        owner_id: 账号所属用户ID。
    Returns:
        tuple: (可能刷新后的 Cookie, 失败返回)，校验通过时失败返回为 None。
    """
    # 编辑不调用 ensure_publish_capability_reliable：判定不可信时最坏结果只是拒绝编辑，
    # 不会像发布那样把鱼小铺商品按个人版落地，因此保留回落个人版判定的结果。
    capability = await detect_publish_account_capability(
        cookie, account_id=account_id, owner_id=owner_id
    )
    cookie = capability.get("cookies_str") or cookie
    if not capability.get("success"):
        return cookie, _fail(
            capability.get("message") or "账号发布能力检测失败，请稍后重试",
            account_invalid=bool(capability.get("account_invalid")),
            cookie=cookie,
        )
    if not capability.get("is_fish_shop"):
        # 检测不可信时不能断言「未开通鱼小铺」：真实原因可能是闲鱼限流/风控/网络异常，
        # 若照抄这句话，用户会误以为是账号权限问题而不会重试
        if not capability.get("detection_reliable", True):
            reason = str(
                capability.get("detection_unreliable_reason") or "鱼小铺后台发布配置暂时取不到"
            )
            return cookie, _fail(
                f"暂时无法确认账号是否开通鱼小铺（{reason}），请稍后重试",
                account_invalid=False,
                cookie=cookie,
            )
        return cookie, _fail(
            "该账号未开通鱼小铺，无法编辑平台商品", account_invalid=False, cookie=cookie
        )
    return cookie, None


async def _fetch_edit_detail(
    *, account_id: str, cookie: str, item_id: str, owner_id: int | None
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """拉取平台商品编辑详情。

    Args:
        account_id: 闲鱼账号标识。
        cookie: 账号 Cookie。
        item_id: 闲鱼商品ID。
        owner_id: 账号所属用户ID。
    Returns:
        tuple: (可能刷新后的 Cookie, 商品详情, 失败返回)，成功时失败返回为 None。
    """
    response = await _call_seller_api(
        account_id=account_id,
        cookie=cookie,
        owner_id=owner_id,
        api=EDIT_DETAIL_API,
        data={"itemId": item_id},
    )
    cookie = response.get("cookies_str") or cookie
    if not response.get("success"):
        logger.error(
            f"闲鱼商品编辑详情接口失败完整返回: account_id={account_id}, item_id={item_id}, "
            f"response={_loggable_response(response)}"
        )
        return (
            cookie,
            None,
            _fail(
                f"获取闲鱼商品详情失败：{response.get('error') or '未知错误'}",
                account_invalid=bool(response.get("account_invalid")),
                cookie=cookie,
            ),
        )
    res = response.get("res") if isinstance(response.get("res"), dict) else {}
    detail = res.get("data") if isinstance(res.get("data"), dict) else None
    if not detail or not _text(detail.get("itemId")):
        logger.error(
            f"闲鱼商品编辑详情返回结构异常: account_id={account_id}, item_id={item_id}, "
            f"res={json.dumps(res, ensure_ascii=False, default=str)}"
        )
        return cookie, None, _fail("闲鱼未返回商品详情，无法编辑", account_invalid=False, cookie=cookie)
    return cookie, detail, None


def _business_failure_message(res: dict[str, Any]) -> str:
    """从 edit 接口返回里识别「ret 成功但业务失败」的情况。

    抓包中 edit 的响应体为空，成功结构未知，因此按通用标志位判断：
    data 里显式的 success=false 或非白名单 code 一律视为失败。

    Args:
        res: mtop 返回的完整响应 JSON。
    Returns:
        str: 失败提示，判定为成功时返回空串。
    """
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    if not data:
        return ""
    message = ""
    for key in ("msg", "message", "errorMsg", "errMsg", "resultMsg", "tips"):
        message = _text(data.get(key))
        if message:
            break
    for key in ("success", "isSuccess"):
        if key in data and data.get(key) in (False, "false", "False"):
            return message or "闲鱼返回编辑失败"
    code = _text(data.get("code")) or _text(data.get("errorCode"))
    if code and code not in _SUCCESS_CODES:
        return message or f"闲鱼返回编辑失败（code={code}）"
    return ""


async def fetch_seller_item_edit_detail(
    *, account_id: str, cookie: str, item_id: str, owner_id: int | None = None
) -> dict[str, Any]:
    """拉取鱼小铺商品详情并转成编辑表单数据。

    Args:
        account_id: 闲鱼账号标识（cookie_id）。
        cookie: 账号 Cookie。
        item_id: 闲鱼商品ID。
        owner_id: 账号所属用户ID。
    Returns:
        dict: {success, message, account_invalid, cookies_str, data:{form}}
    """
    item_id = _text(item_id)
    if not item_id:
        return _fail("缺少闲鱼商品ID，无法编辑", account_invalid=False, cookie=cookie)

    cookie, failure = await _ensure_fish_shop(
        account_id=account_id, cookie=cookie, owner_id=owner_id
    )
    if failure:
        return failure

    cookie, detail, failure = await _fetch_edit_detail(
        account_id=account_id, cookie=cookie, item_id=item_id, owner_id=owner_id
    )
    if failure:
        return failure

    form = map_edit_detail_to_form(detail or {})
    return {
        "success": True,
        "message": "获取商品详情成功",
        "account_invalid": False,
        "cookies_str": cookie,
        "data": {"form": form},
    }


async def edit_seller_item(
    *,
    account_id: str,
    cookie: str,
    item_id: str,
    item_data: dict[str, Any],
    owner_id: int | None = None,
    static_root: str | Path | None = None,
) -> dict[str, Any]:
    """提交鱼小铺商品编辑，载荷与单品发布共用构造器。

    Args:
        account_id: 闲鱼账号标识（cookie_id）。
        cookie: 账号 Cookie。
        item_id: 闲鱼商品ID。
        item_data: 编辑表单数据（字段与单品发布一致）。
        owner_id: 账号所属用户ID。
        static_root: 本地静态文件根目录，解析 /static/... 图片路径使用。
    Returns:
        dict: {success, message, account_invalid, cookies_str, data:None}
    """
    item_id = _text(item_id)
    if not item_id:
        return _fail("缺少闲鱼商品ID，无法编辑", account_invalid=False, cookie=cookie)

    cookie, failure = await _ensure_fish_shop(
        account_id=account_id, cookie=cookie, owner_id=owner_id
    )
    if failure:
        return failure

    # 提交前重新拉取平台详情作为快照，避免用过期数据覆盖平台最新状态
    cookie, snapshot, failure = await _fetch_edit_detail(
        account_id=account_id, cookie=cookie, item_id=item_id, owner_id=owner_id
    )
    if failure:
        return failure

    try:
        payload, cookie = await build_item_payload(
            item_data,
            cookie,
            account_id,
            owner_id,
            static_root=static_root or STATIC_ROOT,
            snapshot=snapshot,
        )
    except DirectPublishError as exc:
        return _fail(str(exc), account_invalid=exc.account_invalid, cookie=cookie)

    # edit 与 publish 的载荷字段完全一致，只多一个 itemId（抓包确认）
    payload["itemId"] = item_id
    # 抓包中 edit 的 itemCatDTO 不带 leafId，平台编辑详情也不返回该字段，为空时不提交
    cat_dto = payload.get("itemCatDTO")
    if isinstance(cat_dto, dict) and not _text(cat_dto.get("leafId")):
        cat_dto.pop("leafId", None)
    response = await _call_seller_api(
        account_id=account_id,
        cookie=cookie,
        owner_id=owner_id,
        api=EDIT_API,
        data={"inputJson": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
    )
    cookie = response.get("cookies_str") or cookie
    # 抓包中 edit 响应体为空，成功结构未知：无论成败都打印完整返回，便于据实收紧判定
    logger.info(
        f"闲鱼商品编辑接口完整返回: account_id={account_id}, item_id={item_id}, "
        f"response={_loggable_response(response)}"
    )
    if not response.get("success"):
        return _fail(
            f"闲鱼接口编辑失败：{response.get('error') or '未知错误'}",
            account_invalid=bool(response.get("account_invalid")),
            cookie=cookie,
        )
    res = response.get("res") if isinstance(response.get("res"), dict) else {}
    business_failure = _business_failure_message(res)
    if business_failure:
        return _fail(f"闲鱼接口编辑失败：{business_failure}", account_invalid=False, cookie=cookie)
    return {
        "success": True,
        "message": "商品编辑成功",
        "account_invalid": False,
        "cookies_str": cookie,
        "data": None,
    }


__all__ = ["edit_seller_item", "fetch_seller_item_edit_detail"]
