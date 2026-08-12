"""
闲鱼平台分类推荐服务。

功能：
1. 按抓包中的 mtop 分类推荐接口提交商品标题和描述。
2. 解析接口实际返回的所有分类候选及动态层级路径。
3. 将第三方请求失败转换为可展示的业务异常，不返回模拟分类数据。
"""
from __future__ import annotations

import hashlib
import asyncio
import json
import re
import time
from typing import Any

import aiohttp
from loguru import logger

from common.utils.cookie_refresh import (
    handle_token_expired_response,
    is_token_expired_error,
    update_account_cookies_in_db,
)


APP_KEY = "34839810"
CATEGORY_RECOMMEND_URL = (
    "https://h5api.m.goofish.com/h5/"
    "mtop.taobao.idle.kgraph.pc.property.recommend/2.0/"
)
REQUEST_TIMEOUT_SECONDS = 20


class CategoryRecommendationError(RuntimeError):
    """分类推荐接口不可用或未返回有效分类时抛出的业务异常。"""


def _get_h5_token(cookie: str) -> str:
    """从 Cookie 中提取 mtop 签名所需的 _m_h5_tk token。"""
    for part in cookie.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == "_m_h5_tk":
            return value.split("_", 1)[0]
    return ""


def _make_sign(timestamp: str, token: str, data: str) -> str:
    """按 mtop 规则生成请求签名。"""
    return hashlib.md5(f"{token}&{timestamp}&{APP_KEY}&{data}".encode("utf-8")).hexdigest()


def _as_text(value: Any) -> str:
    """将接口字段安全转换为去除首尾空格的字符串。"""
    return str(value).strip() if value is not None else ""


def _as_bool(value: Any) -> bool:
    """兼容接口返回的布尔值和字符串布尔值。"""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _build_path(value: dict[str, Any]) -> list[dict[str, str]]:
    """根据响应中实际存在的 channelCatN 字段动态构建分类路径。"""
    path: list[dict[str, str]] = []

    def append_level(category_id: str, category_name: str) -> None:
        if category_id and category_name and (not path or path[-1] != {"id": category_id, "name": category_name}):
            path.append({"id": category_id, "name": category_name})

    level_keys: list[tuple[int, str, str]] = []
    for key, raw_id in value.items():
        match = re.fullmatch(r"channelCat(\d+)Id", str(key))
        if not match:
            continue
        level = int(match.group(1))
        category_id = _as_text(raw_id)
        category_name = _as_text(value.get(f"channelCat{level}Name"))
        if category_id and category_name:
            level_keys.append((level, category_id, category_name))

    for _, category_id, category_name in sorted(level_keys):
        append_level(category_id, category_name)

    channel_id = _as_text(value.get("channelCatId"))
    channel_name = _as_text(value.get("channelCatName"))
    append_level(channel_id, channel_name)

    # 有频道路径时，catId/catName 作为平台末级 ID 单独保存，不再重复显示同一条路径。
    if not path:
        append_level(_as_text(value.get("catId")), _as_text(value.get("catName")))
    return path


def _card_list(response: dict[str, Any]) -> list[dict[str, Any]]:
    """读取推荐接口返回的 cardList，兼容字符串形式的 cardList。"""
    data = response.get("data") or {}
    cards = data.get("cardList") or []
    if isinstance(cards, str):
        try:
            cards = json.loads(cards)
        except json.JSONDecodeError:
            cards = []
    return cards if isinstance(cards, list) else []


def _parse_current_card_list(response: dict[str, Any]) -> list[dict[str, Any]]:
    """保留接口返回的完整 cardData，供下一次分类切换请求作为 currentCardList。

    抓包显示 ``currentCardList`` 包含分类、品牌、成色及当前分类属性的全部卡片，
    不能只保留分类卡；否则平台无法依据刚选中的分类收敛下一轮属性卡。
    """
    card_list: list[dict[str, Any]] = []
    for card in _card_list(response):
        card_data = card.get("cardData") if isinstance(card, dict) else None
        if isinstance(card_data, dict) and _as_text(card_data.get("propertyId")):
            card_list.append(card_data)
    return card_list


def _parse_candidates(response: dict[str, Any]) -> list[dict[str, Any]]:
    """解析分类卡（propertyId=-10000），保留接口实际返回的候选数量。"""
    cards = _card_list(response)

    candidates: list[dict[str, Any]] = []
    for card in cards:
        card_data = card.get("cardData") if isinstance(card, dict) else None
        if not isinstance(card_data, dict):
            continue
        if _as_text(card_data.get("propertyId")) != "-10000":
            continue
        values = card_data.get("valuesList") or []
        for value in values if isinstance(values, list) else []:
            if not isinstance(value, dict):
                continue
            transport = value.get("transportData") if isinstance(value.get("transportData"), dict) else {}
            channel_cat_id = _as_text(value.get("channelCatId")) or _as_text(transport.get("channelCateId"))
            channel_cat_name = _as_text(value.get("channelCatName")) or _as_text(transport.get("channelCateName"))
            cat_name = _as_text(value.get("catName")) or _as_text(transport.get("valueName"))
            tb_cat_id = _as_text(value.get("tbCatId")) or _as_text(transport.get("tbCatId"))
            normalized_value = {
                **transport,
                **value,
                "channelCatId": channel_cat_id,
                "channelCatName": channel_cat_name,
                "catName": cat_name,
                "tbCatId": tb_cat_id,
            }
            path = _build_path(normalized_value)
            if not path and channel_cat_id and channel_cat_name:
                path = [{"id": channel_cat_id, "name": channel_cat_name}]
            if not path:
                continue
            candidates.append(
                {
                    "cat_id": _as_text(value.get("catId")) or None,
                    "cat_name": cat_name or None,
                    "channel_cat_id": channel_cat_id or None,
                    "channel_cat_name": channel_cat_name or None,
                    "leaf_id": _as_text(value.get("leafId")) or None,
                    "tb_cat_id": tb_cat_id or None,
                    "path": path,
                    "score": value.get("score"),
                    "is_selected": _as_bool(value.get("isClicked")) or _as_bool(value.get("isUserClick")),
                }
            )
    return candidates


def _apply_category_predict_result(
    response: dict[str, Any], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """用 categoryPredictResult 补全当前选中分类可能缺失的末级分类ID。

    推荐卡的部分候选只携带频道分类ID，而同一响应的 categoryPredictResult
    会给出当前选中项完整的 catId、channelCatId、tbCatId。发布接口要求三者
    都存在，因此仅对当前命中的候选合并该信息。
    """
    data = response.get("data") or {}
    result = data.get("categoryPredictResult") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        return candidates

    cat_id = _as_text(result.get("catId"))
    cat_name = _as_text(result.get("catName"))
    channel_cat_id = _as_text(result.get("channelCatId"))
    tb_cat_id = _as_text(result.get("tbCatId"))
    if not any((cat_id, cat_name, channel_cat_id, tb_cat_id)):
        return candidates

    for candidate in candidates:
        matches = (
            bool(channel_cat_id and candidate.get("channel_cat_id") == channel_cat_id)
            or bool(tb_cat_id and candidate.get("tb_cat_id") == tb_cat_id)
            or bool(cat_id and candidate.get("cat_id") == cat_id)
            or bool(cat_name and candidate.get("cat_name") == cat_name)
        )
        if not matches:
            continue
        candidate["cat_id"] = candidate.get("cat_id") or cat_id or None
        candidate["cat_name"] = candidate.get("cat_name") or cat_name or None
        candidate["channel_cat_id"] = candidate.get("channel_cat_id") or channel_cat_id or None
        candidate["tb_cat_id"] = candidate.get("tb_cat_id") or tb_cat_id or None
        candidate["is_selected"] = True
        break
    return candidates


def _parse_properties(response: dict[str, Any]) -> list[dict[str, Any]]:
    """解析分类以外的动态平台属性卡及其选项。

    闲鱼推荐接口不会固定返回品牌、成色等字段；每个 cardData 就对应页面上的
    一个输入框，因此这里不写死属性名称，直接透传接口实际返回的卡片数量和选项。
    """
    properties: list[dict[str, Any]] = []
    for card in _card_list(response):
        card_data = card.get("cardData") if isinstance(card, dict) else None
        if not isinstance(card_data, dict):
            continue
        property_id = _as_text(card_data.get("propertyId"))
        property_name = _as_text(card_data.get("propertyName"))
        if not property_id or property_id == "-10000" or not property_name:
            continue

        options: list[dict[str, Any]] = []
        values = card_data.get("valuesList") or []
        for value in values if isinstance(values, list) else []:
            if not isinstance(value, dict):
                continue
            transport = value.get("transportData") if isinstance(value.get("transportData"), dict) else {}
            value_id = _as_text(value.get("valueId")) or _as_text(transport.get("valueId"))
            value_name = _as_text(value.get("valueName")) or _as_text(transport.get("valueName"))
            if not value_name:
                continue
            channel_cat_id = _as_text(value.get("channelCatId")) or _as_text(transport.get("channelCateId"))
            tb_cat_id = _as_text(value.get("tbCatId")) or _as_text(transport.get("tbCatId"))
            options.append(
                {
                    "property_id": property_id,
                    "property_name": property_name,
                    "value_id": value_id or None,
                    "value_name": value_name,
                    "channel_cat_id": channel_cat_id or None,
                    "tb_cat_id": tb_cat_id or None,
                }
            )

        properties.append(
            {
                "property_id": property_id,
                "property_name": property_name,
                "input_word": _as_text(card_data.get("inputWord")) or None,
                "is_multiple": _as_bool(card_data.get("isMultiple")),
                "is_decisive_property": _as_bool(card_data.get("isDecisiveProperty")),
                "options": options,
            }
        )
    return properties


class PlatformCategoryService:
    """调用闲鱼 mtop 接口获取商品分类推荐。"""

    async def recommend(
        self,
        title: str,
        description: str,
        cookie: str,
        account_id: str = "",
        owner_id: int | None = None,
        current_card_list: list[dict[str, Any]] | None = None,
        selected_list: list[dict[str, Any]] | None = None,
        cat_id: str = "",
        cat_name: str = "",
        channel_cat_id: str = "",
    ) -> dict[str, Any]:
        """
        根据标题和描述返回平台分类候选，令牌过期时自动刷新并重试一次。

        Args:
            title: 商品标题。
            description: 商品描述。
            cookie: 当前闲鱼账号Cookie。
        account_id: 闲鱼账号标识，用于日志和Cookie写回。
        owner_id: 账号所属用户ID，确保Cookie更新时保持用户隔离。
        current_card_list: 分类切换时沿用上一次响应中的完整属性卡。
        selected_list: 当前已选分类的属性标签列表。
        cat_id: 当前已选的闲鱼末级分类ID。
        cat_name: 当前已选分类名称。
        channel_cat_id: 当前已选频道分类ID。
        Returns:
            包含接口实际返回分类候选的结果字典。
        Raises:
            CategoryRecommendationError: 请求失败、令牌刷新失败或未返回分类时抛出。
        """
        if not cookie.strip():
            raise CategoryRecommendationError("闲鱼账号缺少Cookie，请先重新登录账号")

        payload = {
            "title": title.strip(),
            "lockCpv": False,
            "multiSKU": False,
            "publishScene": "pcBackendPublish",
            "scene": "shopPcPublish",
            "description": description.strip(),
            "uniqueCode": f"{int(time.time() * 1000)}{account_id[-4:]}",
        }
        if current_card_list:
            payload["currentCardList"] = current_card_list
        if selected_list:
            payload["selectedList"] = selected_list
        if cat_id:
            payload["catId"] = cat_id
        if cat_name:
            payload["catName"] = cat_name
        if channel_cat_id:
            payload["channelCatId"] = channel_cat_id
        data_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            # 禁用 aiohttp 自动 CookieJar，避免它与手动 Cookie 请求头重复或覆盖账号 Cookie。
            async with aiohttp.ClientSession(
                timeout=timeout,
                cookie_jar=aiohttp.DummyCookieJar(),
            ) as client:
                current_cookie = cookie.replace("\n", "").replace("\r", "")
                for retry_count in range(2):
                    token = _get_h5_token(current_cookie)
                    if not token:
                        logger.warning(
                            f"分类推荐Cookie缺少_m_h5_tk，将请求平台获取新令牌: "
                            f"account_id={account_id}, retry_count={retry_count}"
                        )

                    timestamp = str(int(time.time() * 1000))
                    params = {
                        "jsv": "2.7.2",
                        "appKey": APP_KEY,
                        "t": timestamp,
                        "sign": _make_sign(timestamp, token, data_text),
                        "v": "2.0",
                        "type": "originaljson",
                        "accountSite": "xianyu",
                        "dataType": "json",
                        "timeout": str(REQUEST_TIMEOUT_SECONDS * 1000),
                        "api": "mtop.taobao.idle.kgraph.pc.property.recommend",
                        "sessionOption": "AutoLoginOnly",
                        "spm_cnt": "a21107h.42829679.0.0",
                        "spm_pre": "a21107h.42829791.0.0",
                    }
                    headers = {
                        "accept": "application/json",
                        "content-type": "application/x-www-form-urlencoded",
                        "origin": "https://seller.goofish.com",
                        "referer": "https://seller.goofish.com/",
                        "idle_site_biz_code": "COMMONPRO",
                        "idle_user_group_member_id": "",
                        "cookie": current_cookie,
                    }
                    async with client.post(
                        CATEGORY_RECOMMEND_URL,
                        params=params,
                        data={"data": data_text},
                        headers=headers,
                    ) as response:
                        response_text = await response.text()
                        logger.info(
                            f"分类推荐接口完整返回: account_id={account_id}, "
                            f"retry_count={retry_count}, http_status={response.status}, "
                            f"response={response_text}"
                        )
                        body = json.loads(response_text)
                        ret = (body.get("ret") or []) if isinstance(body, dict) else []
                        if is_token_expired_error(ret):
                            if retry_count >= 1:
                                logger.error(
                                    f"分类推荐令牌过期重试已达上限: account_id={account_id}, ret={ret}"
                                )
                                raise CategoryRecommendationError(
                                    "闲鱼账号令牌已过期，自动刷新失败，请重新登录账号"
                                )
                            refreshed, refreshed_cookie = handle_token_expired_response(
                                response,
                                current_cookie,
                            )
                            if not refreshed or refreshed_cookie == current_cookie:
                                raise CategoryRecommendationError(
                                    "闲鱼账号令牌已过期且接口未返回新Cookie，请重新登录账号"
                                )
                            current_cookie = refreshed_cookie
                            saved = await update_account_cookies_in_db(
                                account_id,
                                current_cookie,
                                owner_id=owner_id,
                            )
                            if not saved:
                                logger.error(
                                    f"分类推荐令牌刷新Cookie写库失败: account_id={account_id}, owner_id={owner_id}"
                                )
                            logger.warning(
                                f"分类推荐令牌过期，准备使用新Cookie重试: account_id={account_id}"
                            )
                            continue

                        if not any("SUCCESS" in str(item) for item in ret):
                            message = str(ret[0]) if ret else "闲鱼接口未返回成功状态"
                            logger.warning(
                                f"分类推荐接口业务失败: account_id={account_id}, ret={message}"
                            )
                            raise CategoryRecommendationError(
                                "分类推荐失败，请检查账号登录状态后重试"
                            )

                        candidates = _apply_category_predict_result(body, _parse_candidates(body))
                        properties = _parse_properties(body)
                        current_card_list = _parse_current_card_list(body)
                        if not candidates:
                            raise CategoryRecommendationError("接口未返回可用的商品分类")
                        return {
                            "candidates": candidates,
                            "properties": properties,
                            "card_list": current_card_list,
                            "account_id": account_id,
                        }
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
            logger.warning(f"分类推荐请求失败: account_id={account_id}, error={exc}")
            raise CategoryRecommendationError("分类推荐接口请求失败，请稍后重试") from exc
        except CategoryRecommendationError:
            raise
        except Exception as exc:
            logger.error(f"分类推荐解析异常: account_id={account_id}, error={exc}")
            raise CategoryRecommendationError("分类推荐接口返回异常，请稍后重试") from exc
