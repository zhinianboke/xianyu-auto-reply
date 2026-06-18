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
"""

import time
from typing import Dict

import requests
from loguru import logger

from common.utils.xianyu_utils import generate_sign

# token 接口地址与 appKey
_TOKEN_API_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/"
_APP_KEY = "34839810"


def request_fresh_captcha_url(
    cookie_id: str,
    cookies: Dict[str, str],
    cookies_str: str,
    device_id: str,
) -> Dict[str, object]:
    """凭账号 Cookie 重新请求 token 接口，提取新鲜的滑块验证链接。

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

        logger.info(f"【{cookie_id}】重新请求新鲜的滑块验证链接...")
        resp = requests.post(_TOKEN_API_URL, params=params, data=data, headers=headers, timeout=15)
        res_json = resp.json()

        # 优先判断 token 是否已可用：风控可能已解除，此时接口直接返回成功 accessToken，无需滑块
        if isinstance(res_json, dict):
            ret_value = res_json.get("ret", []) or []
            if any("SUCCESS::调用成功" in str(r) for r in ret_value):
                data_f = res_json.get("data", {}) if isinstance(res_json.get("data"), dict) else {}
                new_token = data_f.get("accessToken")
                if new_token:
                    logger.info(f"【{cookie_id}】重新请求 token 已成功（风控已解除），无需滑块验证")
                    result["token_ok"] = True
                    result["new_token"] = new_token
                    try:
                        result["new_cookies"] = resp.cookies.get_dict() or {}
                    except Exception:
                        result["new_cookies"] = {}
                    return result

        data_field = res_json.get("data", {}) if isinstance(res_json, dict) else {}
        new_url = data_field.get("url") if isinstance(data_field, dict) else None
        if new_url:
            logger.info(f"【{cookie_id}】已获取新鲜验证链接")
            result["fresh_url"] = new_url
            return result

        logger.info(f"【{cookie_id}】重新请求未返回验证链接（可能已不需要验证）")
        return result
    except Exception as e:
        logger.warning(f"【{cookie_id}】重新获取滑块验证链接失败: {e}")
        return result
