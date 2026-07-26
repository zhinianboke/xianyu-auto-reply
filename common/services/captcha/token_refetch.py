"""
滑块验证链接刷新模块（公共）

用途：
    当 punish?x5secdata 验证链接因等待并发槽位 / 浏览器启动而过期（页面显示
    "抱歉，页面访问出现了问题"）时，凭账号 Cookie 同步重新请求 token 接口，拿到一个
    新鲜的验证链接；若此时风控已解除（接口直接下发 accessToken），则返回 token 可用标志，
    调用方据此可跳过滑块流程。

说明：
    本机处理（cookie_token_manager._request_captcha_url_sync）与远程过滑块接口
    （internal /captcha/solve）共用本逻辑，避免在多处重复实现（项目开发规范第 36 条）。
    使用的 token 接口（小程序 / 网页）跟随系统设置 token.api_mode，每次实时查库，
    与 WebSocket 主流程口径一致。
"""

import time
from typing import Dict

import requests
from loguru import logger

from common.services.captcha.token_response import (
    extract_token_captcha_url,
    get_token_captcha_reason,
    is_token_expired_response,
)
from common.services.im_token_api import extract_im_access_token
from common.services.token_api_mode import (
    get_alternate_token_api_mode,
    get_token_api_mode_label,
    get_token_api_name,
    load_token_api_mode_sync,
)
from common.utils.xianyu_utils import generate_sign

# token 接口地址前缀与 appKey
_TOKEN_API_BASE_URL = "https://h5api.m.goofish.com/h5"
_APP_KEY = "34839810"


def _post_token_api(
    cookie_id: str,
    api_mode: str,
    cookies: Dict[str, str],
    cookies_str: str,
    device_id: str,
) -> tuple[object, Dict[str, str]]:
    """同步请求一次 token 接口。

    Args:
        cookie_id: 账号标识（仅用于日志）
        api_mode: Token 获取方式（小程序 / 网页）
        cookies: Cookie 字典（需含 _m_h5_tk 用于签名）
        cookies_str: Cookie 原始字符串（作为请求头 cookie）
        device_id: 设备 ID（拼入请求体 deviceId）

    Returns:
        ``(响应JSON, 接口下发的Cookie)``
    """
    api_name = get_token_api_name(api_mode)
    timestamp = str(int(time.time() * 1000))
    params = {
        "jsv": "2.7.2",
        "appKey": _APP_KEY,
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
    # deviceId 为空时也照常请求：签名只依赖 _m_h5_tk + data_val + 时间戳
    data_val = '{"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"' + (device_id or "") + '"}'
    data = {"data": data_val}

    token = cookies.get("_m_h5_tk", "").split("_")[0] if cookies.get("_m_h5_tk") else ""
    params["sign"] = generate_sign(params["t"], token, data_val)

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
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "referer": "https://www.goofish.com/",
        "origin": "https://www.goofish.com",
        "cookie": cookies_str.replace("\n", "").replace("\r", "") if cookies_str else "",
    }

    logger.info(
        f"【{cookie_id}】重新请求新鲜的滑块验证链接（{get_token_api_mode_label(api_mode)}）..."
    )
    resp = requests.post(
        f"{_TOKEN_API_BASE_URL}/{api_name}/1.0/",
        params=params,
        data=data,
        headers=headers,
        timeout=15,
    )
    res_json = resp.json()
    try:
        response_cookies = dict(resp.cookies.get_dict() or {})
    except Exception:
        response_cookies = {}
    return res_json, response_cookies


def _request_token_api_with_expiry_retry(
    cookie_id: str,
    api_mode: str,
    cookies: Dict[str, str],
    cookies_str: str,
    device_id: str,
) -> tuple[object, Dict[str, str], Dict[str, str], str]:
    """请求指定 Token 接口，并在 mtop 令牌过期时自动重试一次。

    Args:
        cookie_id: 账号标识（仅用于日志）。
        api_mode: 本轮使用的 Token 接口方式。
        cookies: 当前 Cookie 字典。
        cookies_str: 当前 Cookie 字符串。
        device_id: 设备 ID。

    Returns:
        ``(最终响应JSON, 累计响应Cookie, 最新Cookie字典, 最新Cookie字符串)``。
    """
    current_cookies = dict(cookies)
    current_cookies_str = cookies_str
    response_cookie_updates: Dict[str, str] = {}
    response_json: object = None

    for attempt in range(2):
        response_json, response_cookies = _post_token_api(
            cookie_id,
            api_mode,
            current_cookies,
            current_cookies_str,
            device_id,
        )
        if response_cookies:
            response_cookie_updates.update(response_cookies)
            current_cookies.update(response_cookies)
            current_cookies_str = "; ".join(
                f"{key}={value}" for key, value in current_cookies.items()
            )

        if (
            attempt == 0
            and is_token_expired_response(response_json)
            and response_cookies.get("_m_h5_tk")
        ):
            logger.warning(
                f"【{cookie_id}】重取验证链接时命中令牌过期，"
                "使用接口下发的新 _m_h5_tk 重试一次"
            )
            continue
        break

    return (
        response_json,
        response_cookie_updates,
        current_cookies,
        current_cookies_str,
    )


def request_fresh_captcha_url(
    cookie_id: str,
    cookies: Dict[str, str],
    cookies_str: str,
    device_id: str,
) -> Dict[str, object]:
    """凭账号 Cookie 重新请求 token 接口，提取新鲜的滑块验证链接。

    命中 mtop 令牌过期时，用接口下发的新 _m_h5_tk 合并后自动重试一次，
    与其他取 Token 路径的处理口径保持一致。

    Args:
        cookie_id: 账号标识（仅用于日志）
        cookies: Cookie 字典（需含 _m_h5_tk 用于签名）
        cookies_str: Cookie 原始字符串（作为请求头 cookie）
        device_id: 设备 ID（拼入请求体 deviceId）

    Returns:
        dict：
          - token_ok (bool): 风控是否已解除、token 直接可用（无需滑块）
          - new_token (str|None): token_ok 时下发的 accessToken
          - new_cookies (dict): 接口下发的刷新 cookie（可能为空）
          - fresh_url (str|None): 新鲜的验证链接（需要继续过滑块时）
    """
    result: Dict[str, object] = {
        "token_ok": False,
        "new_token": None,
        "new_cookies": {},
        "fresh_url": None,
    }
    try:
        # Token接口方式跟随系统设置实时生效；首选接口触发风控时，自动切换到
        # 另一个接口重试一次，与异步 Token 请求路径保持一致。
        primary_mode = load_token_api_mode_sync(cookie_id)
        current_cookies = dict(cookies)
        current_cookies_str = cookies_str
        primary_response, response_cookies, current_cookies, current_cookies_str = (
            _request_token_api_with_expiry_retry(
                cookie_id,
                primary_mode,
                current_cookies,
                current_cookies_str,
                device_id,
            )
        )
        result["new_cookies"] = dict(response_cookies)
        final_response = primary_response

        captcha_reason = get_token_captcha_reason(primary_response)
        if captcha_reason:
            fallback_mode = get_alternate_token_api_mode(primary_mode)
            logger.warning(
                f"【{cookie_id}】{get_token_api_mode_label(primary_mode)}触发风控"
                f"（{captcha_reason}），重取链接时自动切换到"
                f"{get_token_api_mode_label(fallback_mode)}重试"
            )
            try:
                (
                    fallback_response,
                    fallback_cookies,
                    current_cookies,
                    current_cookies_str,
                ) = _request_token_api_with_expiry_retry(
                    cookie_id,
                    fallback_mode,
                    current_cookies,
                    current_cookies_str,
                    device_id,
                )
                merged_new_cookies = dict(result.get("new_cookies") or {})
                merged_new_cookies.update(fallback_cookies)
                result["new_cookies"] = merged_new_cookies

                # 备用接口只有在拿到 Token 或有效验证链接时才覆盖首选接口结果；
                # 其他失败保留首选接口的可处理滑块链接。
                if extract_im_access_token(fallback_response) or extract_token_captcha_url(
                    fallback_response
                ):
                    final_response = fallback_response
            except Exception as fallback_error:
                logger.warning(
                    f"【{cookie_id}】备用Token接口请求失败，继续使用首选接口验证链接: "
                    f"{fallback_error}"
                )

        new_token = extract_im_access_token(final_response)
        if new_token:
            logger.info(
                f"【{cookie_id}】重新请求 token 已成功（风控已解除），无需滑块验证"
            )
            result["token_ok"] = True
            result["new_token"] = new_token
            return result

        new_url = extract_token_captcha_url(final_response)
        if new_url:
            logger.info(f"【{cookie_id}】已获取新鲜验证链接")
            result["fresh_url"] = new_url
            return result

        logger.info(f"【{cookie_id}】重新请求未返回验证链接（可能已不需要验证）")

        return result
    except Exception as e:
        logger.warning(f"【{cookie_id}】重新获取滑块验证链接失败: {e}")
        return result
