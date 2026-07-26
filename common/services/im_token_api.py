"""
闲鱼 IM Token API 客户端。

功能：
1. 使用账号 Cookie 和指定 Device ID 构造签名请求
2. 支持小程序接口 / 网页接口两种 Token 获取方式
3. 触发风控时自动切换到另一个接口重试一次
4. 返回接口响应及 Set-Cookie 内容
5. 统一解析成功响应中的 accessToken
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any

import aiohttp
from loguru import logger

from common.services.captcha.token_response import get_token_captcha_reason
from common.services.token_api_mode import (
    DEFAULT_TOKEN_API_MODE,
    get_alternate_token_api_mode,
    get_token_api_mode_label,
    get_token_api_name,
    normalize_token_api_mode,
)
from common.utils.xianyu_utils import generate_sign, trans_cookies


IM_TOKEN_API_BASE_URL = "https://h5api.m.goofish.com/h5"


def build_im_token_api_url(api_mode: str = DEFAULT_TOKEN_API_MODE) -> str:
    """按接口方式拼出 Token 接口地址。

    Args:
        api_mode: Token 获取方式（小程序 / 网页）
    Returns:
        完整的 mtop 接口地址
    """
    return f"{IM_TOKEN_API_BASE_URL}/{get_token_api_name(api_mode)}/1.0/"


@dataclass(frozen=True, slots=True)
class ImTokenApiResult:
    """IM Token API 的原始请求结果。"""

    response_json: Any
    response_cookies: dict[str, str]
    status_code: int
    duration_seconds: float
    api_mode: str = DEFAULT_TOKEN_API_MODE


def extract_im_access_token(response_json: Any) -> str | None:
    """从成功响应中提取 IM accessToken。

    Args:
        response_json: IM Token API 返回的 JSON 数据。

    Returns:
        成功时返回非空 accessToken，否则返回 None。
    """
    if not isinstance(response_json, dict):
        return None

    ret_value = response_json.get("ret", []) or []
    if isinstance(ret_value, str):
        ret_value = [ret_value]
    if not any("SUCCESS::调用成功" in str(item) for item in ret_value):
        return None

    data = response_json.get("data")
    if not isinstance(data, dict):
        return None
    access_token = data.get("accessToken")
    return access_token if isinstance(access_token, str) and access_token else None


def _merge_cookies(cookies_str: str, new_cookies: dict[str, str]) -> str:
    """把接口下发的 Set-Cookie 合并回 Cookie 字符串。

    Args:
        cookies_str: 原始 Cookie 字符串。
        new_cookies: 接口响应下发的 Cookie。

    Returns:
        合并后的 Cookie 字符串；无新 Cookie 时原样返回。
    """
    if not new_cookies:
        return cookies_str
    merged = trans_cookies(cookies_str)
    merged.update(new_cookies)
    return "; ".join(f"{key}={value}" for key, value in merged.items())


async def request_im_token(
    cookies_str: str,
    device_id: str,
    *,
    api_mode: str = DEFAULT_TOKEN_API_MODE,
    timeout_seconds: int = 30,
) -> ImTokenApiResult:
    """调用闲鱼 IM Token API。

    Args:
        cookies_str: 账号 Cookie 字符串。
        device_id: 本次请求必须使用的 Device ID。
        api_mode: Token 获取方式（小程序接口 / 网页接口），默认小程序接口。
        timeout_seconds: HTTP 请求总超时秒数。

    Returns:
        包含响应 JSON、响应 Cookie、状态码、耗时和本次接口方式的结果。

    Raises:
        aiohttp.ClientError: 网络请求失败。
        asyncio.TimeoutError: 请求超时。
        ValueError: 响应无法解析为 JSON。
    """
    normalized_mode = normalize_token_api_mode(api_mode)
    api_name = get_token_api_name(normalized_mode)
    timestamp = str(int(time.time() * 1000))
    params = {
        "jsv": "2.7.2",
        "appKey": "34839810",
        "t": timestamp,
        "sign": "",
        "v": "1.0",
        "type": "originaljson",
        "accountSite": "xianyu",
        "dataType": "json",
        "timeout": "20000",
        "api": api_name,
        "sessionOption": "AutoLoginOnly",
        "dangerouslySetWindvaneParams": "%5Bobject%20Object%5D",
        "smToken": "token",
        "queryToken": "sm",
        "sm": "sm",
        "spm_cnt": "a21ybx.im.0.0",
        "spm_pre": "a21ybx.home.sidebar.1.4c053da6vYwnmf",
        "log_id": "4c053da6vYwnmf",
    }
    data_value = (
        '{"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"'
        + device_id
        + '"}'
    )
    cookies = trans_cookies(cookies_str)
    m_h5_token = cookies.get("_m_h5_tk", "")
    signing_token = m_h5_token.split("_")[0] if m_h5_token else ""
    params["sign"] = generate_sign(timestamp, signing_token, data_value)

    headers = {
        "accept": "application/json",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/139.0.0.0 Safari/537.36"
        ),
        "referer": "https://www.goofish.com/",
        "origin": "https://www.goofish.com",
        "cookie": cookies_str.replace("\n", "").replace("\r", "") if cookies_str else "",
    }

    started_at = time.time()
    async with aiohttp.ClientSession() as session:
        async with session.post(
            build_im_token_api_url(normalized_mode),
            params=params,
            data={"data": data_value},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout_seconds),
        ) as response:
            # 风控响应的 content-type 可能不是 json，统一放开校验避免解析异常
            response_json = await response.json(content_type=None)
            response_cookies: dict[str, str] = {}
            for cookie_header in response.headers.getall("set-cookie", []):
                if "=" not in cookie_header:
                    continue
                name, value = cookie_header.split(";", 1)[0].split("=", 1)
                response_cookies[name.strip()] = value.strip()
            return ImTokenApiResult(
                response_json=response_json,
                response_cookies=response_cookies,
                status_code=response.status,
                duration_seconds=time.time() - started_at,
                api_mode=normalized_mode,
            )


async def request_im_token_with_fallback(
    cookies_str: str,
    device_id: str,
    *,
    api_mode: str = DEFAULT_TOKEN_API_MODE,
    timeout_seconds: int = 30,
    log_tag: str = "",
) -> ImTokenApiResult:
    """调用 Token 接口，触发风控时自动切换到另一个接口重试一次。

    切换仅作用于本次调用，不修改系统设置：下次仍从用户选择的接口开始。
    两个接口都被风控时返回「另一个接口」的响应，由调用方按既有逻辑走滑块流程。

    Args:
        cookies_str: 账号 Cookie 字符串。
        device_id: 本次请求必须使用的 Device ID。
        api_mode: 首选的 Token 获取方式。
        timeout_seconds: HTTP 请求总超时秒数。
        log_tag: 日志前缀标识（如账号 ID），仅用于日志定位。

    Returns:
        最终采用的接口响应结果，``api_mode`` 字段标明实际生效的接口方式。

    Raises:
        aiohttp.ClientError: 网络请求失败。
        asyncio.TimeoutError: 请求超时。
    """
    prefix = f"【{log_tag}】" if log_tag else ""
    primary_mode = normalize_token_api_mode(api_mode)
    result = await request_im_token(
        cookies_str,
        device_id,
        api_mode=primary_mode,
        timeout_seconds=timeout_seconds,
    )

    # 成功或非风控失败（如令牌过期、Session过期）都不切换，交回调用方原有逻辑处理
    if extract_im_access_token(result.response_json):
        return result
    captcha_reason = get_token_captcha_reason(result.response_json)
    if not captcha_reason:
        return result

    fallback_mode = get_alternate_token_api_mode(primary_mode)
    logger.warning(
        f"{prefix}{get_token_api_mode_label(primary_mode)}触发风控（{captcha_reason}），"
        f"本次自动切换到{get_token_api_mode_label(fallback_mode)}重试"
    )
    # 首个接口下发的 Cookie（可能含新 _m_h5_tk）需带入重试请求，
    # 与项目既有的「合并响应 Cookie 后重试」口径一致
    fallback_cookies_str = _merge_cookies(cookies_str, result.response_cookies)
    fallback_result = await request_im_token(
        fallback_cookies_str,
        device_id,
        api_mode=fallback_mode,
        timeout_seconds=timeout_seconds,
    )

    # 两次请求下发的 Cookie 都要交回调用方写库，避免切换过程中丢失 Cookie 更新
    merged_response_cookies = dict(result.response_cookies)
    merged_response_cookies.update(fallback_result.response_cookies)
    fallback_result = replace(fallback_result, response_cookies=merged_response_cookies)

    if extract_im_access_token(fallback_result.response_json):
        logger.warning(
            f"{prefix}切换到{get_token_api_mode_label(fallback_mode)}后取Token成功"
        )
        return fallback_result

    logger.warning(
        f"{prefix}{get_token_api_mode_label(fallback_mode)}同样未取到Token，"
        "按原有流程处理（滑块验证等）"
    )
    return fallback_result
