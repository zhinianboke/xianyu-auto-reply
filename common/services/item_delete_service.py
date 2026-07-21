"""
闲鱼商品删除 API 服务。

功能：
1. 调用 mtop.alibaba.idle.seller.pc.item.delete 删除闲鱼平台商品
2. 合并响应 Set-Cookie，并在令牌过期或为空时重新签名重试
3. 支持复用 HTTP 会话顺序批量删除，返回每个商品的具体结果
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import aiohttp
from loguru import logger

from common.services.account_cookie_service import merge_account_cookie_fields
from common.utils.cookie_refresh import (
    extract_cookies_from_response,
    is_token_expired_error,
    is_session_expired_error,
    mark_account_session_expired,
    merge_cookies,
    trigger_password_login_async,
    update_account_cookies_in_db,
)
from common.utils.xianyu_utils import generate_sign, trans_cookies


DELETE_ITEM_API = "mtop.alibaba.idle.seller.pc.item.delete"
DELETE_ITEM_URL = f"https://h5api.m.goofish.com/h5/{DELETE_ITEM_API}/1.0/"
MAX_TOKEN_RETRY = 1
MAX_NETWORK_RETRY = 1
REQUEST_TIMEOUT = 20


def _clean_item_ids(item_ids: list[str]) -> list[str]:
    """过滤空商品 ID，并按输入顺序去重。"""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw_item_id in item_ids or []:
        item_id = str(raw_item_id or "").strip()
        if item_id and item_id not in seen:
            seen.add(item_id)
            cleaned.append(item_id)
    return cleaned


async def _persist_response_cookies(
    *,
    account_id: str,
    account_row_id: int | None,
    owner_id: int | None,
    cookies_str: str,
    response: aiohttp.ClientResponse,
) -> tuple[str, bool, str, bool]:
    """合并并持久化删除接口下发的 Cookie。"""
    new_cookies = extract_cookies_from_response(response)
    if not new_cookies:
        return cookies_str, True, "未返回新Cookie", False

    merged_cookies_str = merge_cookies(cookies_str, new_cookies)
    if account_row_id is not None and account_row_id > 0:
        saved_cookies_str = await merge_account_cookie_fields(
            account_row_id,
            account_id,
            new_cookies,
        )
        if saved_cookies_str:
            return (
                saved_cookies_str,
                True,
                f"已更新{len(new_cookies)}个Cookie字段",
                True,
            )
        return merged_cookies_str, False, "删除接口Cookie合并写回失败", True

    saved = await update_account_cookies_in_db(
        account_id,
        merged_cookies_str,
        owner_id=owner_id,
    )
    return (
        merged_cookies_str,
        saved,
        f"已更新{len(new_cookies)}个Cookie字段" if saved else "删除接口Cookie写回失败",
        True,
    )


async def _delete_item_with_session(
    *,
    http_session: aiohttp.ClientSession,
    account_id: str,
    cookies_str: str,
    item_id: str,
    retry_count: int,
    account_row_id: int | None,
    owner_id: int | None,
) -> dict[str, Any]:
    """使用指定 HTTP 会话删除一个商品。"""
    current_cookies = cookies_str
    cookie_saved = True
    cookie_message = "未返回新Cookie"
    token_retries = max(0, retry_count)
    network_retries = 0

    while True:
        try:
            cookies = trans_cookies(current_cookies)
            timestamp = str(int(time.time() * 1000))
            data_value = json.dumps(
                {"itemId": str(item_id), "draftId": None},
                separators=(",", ":"),
            )
            m_h5_token = cookies.get("_m_h5_tk", "")
            signing_token = m_h5_token.split("_")[0] if m_h5_token else ""
            params = {
                "jsv": "2.7.2",
                "appKey": "34839810",
                "t": timestamp,
                "sign": generate_sign(timestamp, signing_token, data_value),
                "v": "1.0",
                "type": "originaljson",
                "accountSite": "xianyu",
                "dataType": "json",
                "timeout": "20000",
                "needLoginPC": "true",
                "showErrorToast": "true",
                "api": DELETE_ITEM_API,
                "sessionOption": "AutoLoginOnly",
                "spm_cnt": "a21107h.42829799.0.0",
            }
            headers = {
                "accept": "application/json",
                "accept-language": "en,zh-CN;q=0.9,zh;q=0.8",
                "cache-control": "no-cache",
                "content-type": "application/x-www-form-urlencoded",
                "idle_site_biz_code": "COMMONPRO",
                "idle_user_group_member_id": "",
                "pragma": "no-cache",
                "priority": "u=1, i",
                "sec-ch-ua": (
                    '"Google Chrome";v="146", "Not=A?Brand";v="8", '
                    '"Chromium";v="146"'
                ),
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "user-agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36"
                ),
                "referer": "https://seller.goofish.com/?site=COMMONPRO",
                "cookie": current_cookies.replace("\n", "").replace("\r", ""),
            }

            async with http_session.post(
                DELETE_ITEM_URL,
                params=params,
                data={"data": data_value},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                response_json = await response.json(content_type=None)
                (
                    current_cookies,
                    response_cookie_saved,
                    cookie_message,
                    response_cookie_received,
                ) = (
                    await _persist_response_cookies(
                        account_id=account_id,
                        account_row_id=account_row_id,
                        owner_id=owner_id,
                        cookies_str=current_cookies,
                        response=response,
                    )
                )
                cookie_saved = cookie_saved and response_cookie_saved
            network_retries = 0

            raw_ret = response_json.get("ret", []) if isinstance(response_json, dict) else []
            if isinstance(raw_ret, str):
                ret = [raw_ret]
            elif isinstance(raw_ret, list):
                ret = raw_ret
            else:
                ret = [str(raw_ret)] if raw_ret else []
            ret_text = str(ret[0]) if ret else ""
            if "SUCCESS" in ret_text:
                data = response_json.get("data", {})
                data_success = data is True
                if isinstance(data, dict):
                    data_success = (
                        str(data.get("code") or "").lower() == "success"
                        or data.get("data") is True
                        or data.get("success") is True
                    )
                if data_success:
                    logger.info(f"【{account_id}】删除闲鱼商品[{item_id}]成功")
                    return {
                        "success": True,
                        "message": "删除成功",
                        "item_id": item_id,
                        "cookies_str": current_cookies,
                        "cookie_saved": cookie_saved,
                        "cookie_message": cookie_message,
                    }
                detail = data.get("msg", "") if isinstance(data, dict) else ""
                message = str(detail or data or "删除接口返回失败")
                return {
                    "success": False,
                    "message": message,
                    "item_id": item_id,
                    "cookies_str": current_cookies,
                    "cookie_saved": cookie_saved,
                    "cookie_message": cookie_message,
                }

            if is_token_expired_error(ret):
                if token_retries >= MAX_TOKEN_RETRY:
                    return {
                        "success": False,
                        "message": f"令牌过期重试已达上限: {ret_text}",
                        "item_id": item_id,
                        "cookies_str": current_cookies,
                        "cookie_saved": cookie_saved,
                        "cookie_message": cookie_message,
                    }
                if not response_cookie_received:
                    return {
                        "success": False,
                        "message": f"令牌过期，但响应未返回新Cookie，无法重签重试: {ret_text}",
                        "item_id": item_id,
                        "cookies_str": current_cookies,
                        "cookie_saved": cookie_saved,
                        "cookie_message": cookie_message,
                    }
                token_retries += 1
                logger.warning(
                    f"【{account_id}】删除闲鱼商品[{item_id}]令牌过期，"
                    f"使用最新Cookie重试({token_retries}/{MAX_TOKEN_RETRY})"
                )
                continue

            if is_session_expired_error(ret):
                recovery_started = False
                try:
                    mark_account_session_expired(account_id)
                    trigger_password_login_async(account_id)
                    recovery_started = True
                except Exception as recovery_exc:
                    logger.error(
                        f"【{account_id}】删除闲鱼商品[{item_id}]触发Session恢复失败: "
                        f"{type(recovery_exc).__name__}: {recovery_exc}"
                    )
                recovery_message = (
                    "Session已过期，已触发后台密码登录，请稍后重试"
                    if recovery_started
                    else "Session已过期，触发后台密码登录失败，请稍后重试"
                )
                return {
                    "success": False,
                    "message": f"{recovery_message}: {ret_text}",
                    "item_id": item_id,
                    "cookies_str": current_cookies,
                    "cookie_saved": cookie_saved,
                    "cookie_message": cookie_message,
                    "session_expired": True,
                    "session_recovery_triggered": recovery_started,
                }

            return {
                "success": False,
                "message": ret_text or "删除失败",
                "item_id": item_id,
                "cookies_str": current_cookies,
                "cookie_saved": cookie_saved,
                "cookie_message": cookie_message,
            }
        except (aiohttp.ClientError, TimeoutError) as exc:
            if network_retries < MAX_NETWORK_RETRY:
                network_retries += 1
                logger.warning(
                    f"【{account_id}】删除闲鱼商品[{item_id}]网络失败，"
                    f"准备重试({network_retries}/{MAX_NETWORK_RETRY}): {exc}"
                )
                await asyncio.sleep(0.2)
                continue
            logger.warning(
                f"【{account_id}】删除闲鱼商品[{item_id}]网络重试仍失败: {exc}"
            )
            return {
                "success": False,
                "message": f"网络重试仍失败: {type(exc).__name__}: {exc}",
                "item_id": item_id,
                "cookies_str": current_cookies,
                "cookie_saved": cookie_saved,
                "cookie_message": cookie_message,
            }
        except Exception as exc:
            logger.error(f"【{account_id}】删除闲鱼商品[{item_id}]异常: {exc}")
            return {
                "success": False,
                "message": f"删除异常: {type(exc).__name__}: {exc}",
                "item_id": item_id,
                "cookies_str": current_cookies,
                "cookie_saved": cookie_saved,
                "cookie_message": cookie_message,
            }


async def delete_item_from_xianyu(
    account_id: str,
    cookies_str: str,
    item_id: str,
    retry_count: int = 0,
    *,
    account_row_id: int | None = None,
    owner_id: int | None = None,
) -> dict[str, Any]:
    """删除一个闲鱼平台商品，令牌过期时自动重试一次。"""
    clean_item_id = str(item_id or "").strip()
    if not clean_item_id:
        return {
            "success": False,
            "message": "商品ID不能为空",
            "item_id": "",
            "cookies_str": cookies_str,
            "cookie_saved": True,
            "cookie_message": "未调用删除接口",
        }
    async with aiohttp.ClientSession() as http_session:
        return await _delete_item_with_session(
            http_session=http_session,
            account_id=account_id,
            cookies_str=cookies_str,
            item_id=clean_item_id,
            retry_count=retry_count,
            account_row_id=account_row_id,
            owner_id=owner_id,
        )


async def batch_delete_items_from_xianyu(
    *,
    account_id: str,
    cookies_str: str,
    item_ids: list[str],
    account_row_id: int | None = None,
    owner_id: int | None = None,
) -> dict[str, Any]:
    """按顺序批量删除闲鱼平台商品，确保每项使用上一项返回的最新 Cookie。"""
    cleaned_ids = _clean_item_ids(item_ids)
    if not cleaned_ids:
        return {
            "success": False,
            "message": "没有有效的商品ID",
            "success_count": 0,
            "fail_count": 0,
            "results": [],
        }

    current_cookies = cookies_str
    results: list[dict[str, Any]] = []
    async with aiohttp.ClientSession() as http_session:
        for item_index, item_id in enumerate(cleaned_ids):
            result = await _delete_item_with_session(
                http_session=http_session,
                account_id=account_id,
                cookies_str=current_cookies,
                item_id=item_id,
                retry_count=0,
                account_row_id=account_row_id,
                owner_id=owner_id,
            )
            current_cookies = str(result.get("cookies_str") or current_cookies)
            results.append(
                {
                    "item_id": item_id,
                    "success": bool(result.get("success")),
                    "message": str(result.get("message") or "未知错误"),
                    "cookie_saved": bool(result.get("cookie_saved", True)),
                    "cookie_message": str(
                        result.get("cookie_message") or "Cookie处理状态未知"
                    ),
                    "session_recovery_triggered": bool(
                        result.get("session_recovery_triggered", False)
                    ),
                    "session_expired": bool(result.get("session_expired", False)),
                }
            )
            if result.get("session_expired"):
                for remaining_item_id in cleaned_ids[item_index + 1 :]:
                    results.append(
                        {
                            "item_id": remaining_item_id,
                            "success": False,
                            "message": "账号Session已过期，本批次已停止删除",
                            "cookie_saved": True,
                            "cookie_message": "未调用删除接口",
                            "session_recovery_triggered": bool(
                                result.get("session_recovery_triggered", False)
                            ),
                            "session_expired": True,
                        }
                    )
                break

    success_count = sum(1 for result in results if result["success"])
    fail_count = len(results) - success_count
    cookie_fail_count = sum(1 for result in results if not result["cookie_saved"])
    message = f"闲鱼商品删除成功 {success_count} 个，失败 {fail_count} 个"
    if cookie_fail_count:
        message = f"{message}；{cookie_fail_count} 个请求的Cookie写回失败"
    return {
        "success": success_count > 0,
        "message": message,
        "success_count": success_count,
        "fail_count": fail_count,
        "results": results,
    }
