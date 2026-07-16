"""
闲鱼 IM Token API 客户端。

功能：
1. 使用账号 Cookie 和指定 Device ID 构造签名请求
2. 返回接口响应及 Set-Cookie 内容
3. 统一解析成功响应中的 accessToken
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from common.utils.xianyu_utils import generate_sign, trans_cookies


IM_TOKEN_API_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/"


@dataclass(frozen=True, slots=True)
class ImTokenApiResult:
    """IM Token API 的原始请求结果。"""

    response_json: Any
    response_cookies: dict[str, str]
    status_code: int
    duration_seconds: float


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


async def request_im_token(
    cookies_str: str,
    device_id: str,
    *,
    timeout_seconds: int = 30,
) -> ImTokenApiResult:
    """调用闲鱼 IM Token API。

    Args:
        cookies_str: 账号 Cookie 字符串。
        device_id: 本次请求必须使用的 Device ID。
        timeout_seconds: HTTP 请求总超时秒数。

    Returns:
        包含响应 JSON、响应 Cookie、状态码和耗时的结果。

    Raises:
        aiohttp.ClientError: 网络请求失败。
        asyncio.TimeoutError: 请求超时。
        ValueError: 响应无法解析为 JSON。
    """
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
        "api": "mtop.taobao.idlemessage.pc.login.token",
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
            IM_TOKEN_API_URL,
            params=params,
            data={"data": data_value},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout_seconds),
        ) as response:
            response_json = await response.json()
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
            )
