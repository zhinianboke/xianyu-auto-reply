"""
闲鱼 IM Token API 客户端。

功能：
1. 使用账号 Cookie 和指定 Device ID 构造签名请求
2. 支持网页接口 / 远程接口两种 Token 获取方式
3. 返回接口响应及 Set-Cookie 内容
4. 统一解析成功响应中的 accessToken
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace
from typing import Any

import aiohttp
from loguru import logger

from common.services.captcha.token_response import is_token_expired_response
from common.services.token_api_mode import (
    DEFAULT_TOKEN_API_MODE,
    TOKEN_API_MODE_REMOTE,
    TOKEN_API_MODE_WEB,
    get_token_api_name,
    normalize_token_api_mode,
)
from common.services.remote_token_api import (
    RemoteTokenResult,
    load_remote_token_settings,
    request_remote_xianyu_token_from_settings,
    validate_remote_token_settings,
)
from common.services.remote_token_risk_log_service import record_remote_token_risk_log
from common.utils.xianyu_utils import generate_sign, trans_cookies


IM_TOKEN_API_BASE_URL = "https://h5api.m.goofish.com/h5"
REMOTE_FALLBACK_EVENT_DESCRIPTION = "本地网页Token接口获取失败后调用远程接口"
# 远程接口取 Token 超时时的最大尝试次数（首次 + 重试 2 次）；全部超时后才交由上层处理滑块
REMOTE_TOKEN_TIMEOUT_MAX_ATTEMPTS = 3
# 远程接口超时重试之间的等待秒数
REMOTE_TOKEN_TIMEOUT_RETRY_DELAY_SECONDS = 1.0


def build_im_token_api_url(api_mode: str = DEFAULT_TOKEN_API_MODE) -> str:
    """按接口方式拼出 Token 接口地址。

    Args:
        api_mode: Token 获取方式（网页）
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
    device_id: str = ""


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


def _merge_cookie_string(cookies_str: str, cookie_updates: dict[str, str]) -> str:
    """把接口下发的 Cookie 合并到下一次本地请求。

    Args:
        cookies_str: 当前 Cookie 字符串。
        cookie_updates: 接口响应下发的 Cookie。
    Returns:
        合并后的 Cookie 字符串。
    """
    merged_cookies = trans_cookies(cookies_str)
    merged_cookies.update(cookie_updates)
    return "; ".join(f"{key}={value}" for key, value in merged_cookies.items())


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
        api_mode: Token 获取方式（网页接口）。
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
                device_id=device_id,
            )


def _remote_result_to_im_token_result(
    result: RemoteTokenResult,
    current_device_id: str,
) -> ImTokenApiResult:
    """把远程 Token 接口结果转换为项目既有 IM Token 响应结构。

    Args:
        result: 远程接口调用结果。
        current_device_id: 当前账号正在使用的设备 ID，远程失败时用于兜底。
    Returns:
        兼容 ``extract_im_access_token`` 的结果对象。
    """
    if result.success:
        response_json = {
            "ret": ["SUCCESS::调用成功"],
            "data": {
                "accessToken": result.token,
                "deviceId": result.device_id,
                "apiMode": result.api_mode,
            },
        }
        return ImTokenApiResult(
            response_json=response_json,
            response_cookies={},
            status_code=result.status_code,
            duration_seconds=result.duration_seconds,
            api_mode=TOKEN_API_MODE_REMOTE,
            device_id=result.device_id,
        )

    return ImTokenApiResult(
        response_json={
            "ret": [f"FAIL::{result.message or '远程接口取Token失败'}"],
            "data": result.response_json,
        },
        response_cookies={},
        status_code=result.status_code,
        duration_seconds=result.duration_seconds,
        api_mode=TOKEN_API_MODE_REMOTE,
        device_id=current_device_id,
    )


async def _request_remote_token_from_settings(
    device_id: str,
    *,
    cookies: str,
    timeout_seconds: int,
    log_tag: str,
    event_description: str,
) -> ImTokenApiResult:
    """调用远程 Token 接口并记录完整的风控日志。

    远程接口请求超时（asyncio.TimeoutError）时，最多尝试
    ``REMOTE_TOKEN_TIMEOUT_MAX_ATTEMPTS`` 次（首次 + 重试 2 次）；
    连续全部超时才向调用方抛出，由上层回退逻辑继续处理滑块。
    非超时异常（如连接、SSL、解析错误）不重试，直接抛出。

    Args:
        device_id: 当前账号的设备 ID。
        cookies: 当前账号完整 Cookie 字符串，传给远程接口 data.cookies。
        timeout_seconds: 单次 HTTP 请求总超时时间。
        log_tag: 账号标识，用于日志定位。
        event_description: 风控日志事件说明。
    Returns:
        统一的 Token 接口响应结果。
    Raises:
        Exception: 远程请求连续超时，或发生非超时异常时向调用方抛出。
    """
    prefix = f"【{log_tag}】" if log_tag else ""
    remote_result = None
    for attempt in range(1, REMOTE_TOKEN_TIMEOUT_MAX_ATTEMPTS + 1):
        try:
            remote_result = await request_remote_xianyu_token_from_settings(
                cookies=cookies,
                timeout_seconds=timeout_seconds,
            )
            break
        except asyncio.TimeoutError as exc:
            # 仅「超时」才重试；其余异常走下面的分支，不重试
            message = f"{type(exc).__name__}: {exc}"
            if attempt < REMOTE_TOKEN_TIMEOUT_MAX_ATTEMPTS:
                logger.warning(
                    f"{prefix}远程接口取Token超时（第{attempt}/"
                    f"{REMOTE_TOKEN_TIMEOUT_MAX_ATTEMPTS}次），"
                    f"{REMOTE_TOKEN_TIMEOUT_RETRY_DELAY_SECONDS}秒后重试: {message}"
                )
                await asyncio.sleep(REMOTE_TOKEN_TIMEOUT_RETRY_DELAY_SECONDS)
                continue
            # 最后一次仍超时：记录风控日志并抛出，交由上层处理滑块
            logger.warning(
                f"{prefix}远程接口取Token连续{REMOTE_TOKEN_TIMEOUT_MAX_ATTEMPTS}次超时，"
                "放弃远程接口，交由上层继续处理滑块"
            )
            await record_remote_token_risk_log(
                account_identifier=log_tag,
                success=False,
                message=f"连续{REMOTE_TOKEN_TIMEOUT_MAX_ATTEMPTS}次超时: {message}",
                event_description=event_description,
            )
            raise
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            logger.warning(f"{prefix}远程接口取Token异常: {message}")
            await record_remote_token_risk_log(
                account_identifier=log_tag,
                success=False,
                message=message,
                event_description=event_description,
            )
            raise

    if remote_result.success:
        logger.info(
            f"{prefix}远程接口取Token成功，实际接口="
            f"{remote_result.api_mode or '未返回'}，耗时={remote_result.duration_seconds:.2f}秒"
        )
    else:
        logger.warning(
            f"{prefix}远程接口取Token失败: {remote_result.message or '未返回错误说明'}"
        )
    await record_remote_token_risk_log(
        account_identifier=log_tag,
        success=remote_result.success,
        message=remote_result.message,
        api_mode=remote_result.api_mode,
        status_code=remote_result.status_code,
        duration_seconds=remote_result.duration_seconds,
        event_description=event_description,
    )
    return _remote_result_to_im_token_result(remote_result, device_id)


async def _try_remote_token_fallback(
    device_id: str,
    *,
    cookies: str,
    timeout_seconds: int,
    log_tag: str,
    local_failure_reason: str,
) -> ImTokenApiResult | None:
    """在远程接口已配置时，尝试作为本地网页接口的回退。

    Args:
        device_id: 当前账号的设备 ID。
        cookies: 当前账号完整 Cookie 字符串，传给远程接口 data.cookies。
        timeout_seconds: HTTP 请求总超时时间。
        log_tag: 账号标识，用于日志定位。
        local_failure_reason: 本地接口失败原因。
    Returns:
        已调用远程接口时返回响应结果；远程未配置或读取失败时返回 None。
    """
    prefix = f"【{log_tag}】" if log_tag else ""
    try:
        remote_settings = await load_remote_token_settings()
    except Exception as exc:
        logger.warning(
            f"{prefix}本地网页接口获取Token失败（{local_failure_reason}），"
            f"读取远程接口配置失败，跳过远程回退: {type(exc).__name__}: {exc}"
        )
        return None

    config_error = validate_remote_token_settings(
        remote_settings.url,
        remote_settings.secret_key,
    )
    if config_error:
        logger.info(
            f"{prefix}本地网页接口获取Token失败（{local_failure_reason}），"
            f"远程接口未配置，跳过远程回退: {config_error}"
        )
        return None

    logger.warning(
        f"{prefix}本地网页接口获取Token失败（{local_failure_reason}），"
        "开始调用远程接口获取Token"
    )
    try:
        return await _request_remote_token_from_settings(
            device_id,
            cookies=cookies,
            timeout_seconds=timeout_seconds,
            log_tag=log_tag,
            event_description=(
                f"{REMOTE_FALLBACK_EVENT_DESCRIPTION}：{local_failure_reason}"
            ),
        )
    except Exception as exc:
        logger.warning(
            f"{prefix}本地网页接口获取Token失败后的远程回退异常: "
            f"{type(exc).__name__}: {exc}"
        )
        return None


async def request_im_token_with_fallback(
    cookies_str: str,
    device_id: str,
    *,
    api_mode: str = DEFAULT_TOKEN_API_MODE,
    timeout_seconds: int = 30,
    log_tag: str = "",
) -> ImTokenApiResult:
    """按系统设置调用 Token 接口。

    网页模式仅调用本地网页端接口；远程模式同样先调用本地网页端接口，
    本地未取得有效 Token 时才调用远程接口。远程也失败时保留本地响应，
    由调用方继续处理滑块或令牌过期。

    Args:
        cookies_str: 账号 Cookie 字符串。
        device_id: 本次请求必须使用的 Device ID。
        api_mode: Token 获取方式。
        timeout_seconds: HTTP 请求总超时秒数。
        log_tag: 日志前缀标识（如账号 ID），仅用于日志定位。

    Returns:
        接口响应结果，``api_mode`` 字段标明实际生效的接口方式。

    Raises:
        aiohttp.ClientError: 网络请求失败。
        asyncio.TimeoutError: 请求超时。
    """
    configured_mode = normalize_token_api_mode(api_mode)
    remote_fallback_enabled = configured_mode == TOKEN_API_MODE_REMOTE

    try:
        local_result = await request_im_token(
            cookies_str,
            device_id,
            api_mode=TOKEN_API_MODE_WEB,
            timeout_seconds=timeout_seconds,
        )
    except Exception as local_error:
        if not remote_fallback_enabled:
            raise
        remote_result = await _try_remote_token_fallback(
            device_id,
            cookies=cookies_str,
            timeout_seconds=timeout_seconds,
            log_tag=log_tag,
            local_failure_reason=f"请求异常：{type(local_error).__name__}: {local_error}",
        )
        if remote_result and extract_im_access_token(remote_result.response_json):
            return remote_result
        raise

    if extract_im_access_token(local_result.response_json):
        return local_result

    if not remote_fallback_enabled:
        return local_result

    local_failure_reason = "未返回有效Token"
    if (
        is_token_expired_response(local_result.response_json)
        and local_result.response_cookies.get("_m_h5_tk")
    ):
        prefix = f"【{log_tag}】" if log_tag else ""
        logger.warning(
            f"{prefix}本地网页端接口返回令牌过期，"
            "合并新 _m_h5_tk 后使用本地接口重试一次"
        )
        retry_cookies_str = _merge_cookie_string(
            cookies_str,
            local_result.response_cookies,
        )
        try:
            retried_local_result = await request_im_token(
                retry_cookies_str,
                device_id,
                api_mode=TOKEN_API_MODE_WEB,
                timeout_seconds=timeout_seconds,
            )
        except Exception as local_retry_error:
            remote_result = await _try_remote_token_fallback(
                device_id,
                cookies=cookies_str,
                timeout_seconds=timeout_seconds,
                log_tag=log_tag,
                local_failure_reason=(
                    "令牌过期后本地重试异常："
                    f"{type(local_retry_error).__name__}: {local_retry_error}"
                ),
            )
            if remote_result and extract_im_access_token(remote_result.response_json):
                return replace(
                    remote_result,
                    response_cookies=local_result.response_cookies,
                )
            return local_result

        cumulative_response_cookies = dict(local_result.response_cookies)
        cumulative_response_cookies.update(retried_local_result.response_cookies)
        local_result = replace(
            retried_local_result,
            response_cookies=cumulative_response_cookies,
        )
        if extract_im_access_token(local_result.response_json):
            return local_result
        local_failure_reason = "令牌过期后本地重试仍未返回有效Token"

    remote_result = await _try_remote_token_fallback(
        device_id,
        cookies=cookies_str,
        timeout_seconds=timeout_seconds,
        log_tag=log_tag,
        local_failure_reason=local_failure_reason,
    )
    if remote_result and extract_im_access_token(remote_result.response_json):
        # 保留本地接口下发的 Cookie，避免本地响应更新的 _m_h5_tk 丢失。
        return replace(
            remote_result,
            response_cookies=local_result.response_cookies,
        )
    return local_result
