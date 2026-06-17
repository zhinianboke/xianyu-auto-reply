"""
闲鱼 mtop 接口统一调用模块

功能：
1. 统一封装闲鱼网页版 mtop 接口（h5api.m.goofish.com）的签名、请求与错误处理
2. 令牌过期（FAIL_SYS_TOKEN_EXOIRED/EXPIRED）：从响应 Set-Cookie 取新 _m_h5_tk 重签重试，
   成功后把刷新的 Cookie 写回数据库
3. Session 过期（FAIL_SYS_SESSION_EXPIRED）：标记冷却 + 触发后台密码登录，并返回需切换账号
4. 触发验证/被挤爆（FAIL_SYS_USER_VALIDATE / RGV587 / 挤爆 / punish 等风控）：返回需切换账号

供采集（搜索）、卖家ID补全（详情）、自动下单等定时任务的 mtop 客户端复用，
统一令牌刷新与账号切换逻辑，避免各处重复实现。

说明：私信走 WebSocket 长连接，由 WebSocket 服务自身的 Cookie/Token 管理处理，不经过本模块。
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Dict, Optional

import aiohttp
from loguru import logger

from common.utils.cookie_refresh import (
    extract_cookies_from_response,
    is_session_expired_error,
    mark_account_session_expired,
    merge_cookies,
    trigger_password_login_async,
    update_account_cookies_in_db,
)
from common.utils.xianyu_utils import generate_sign, trans_cookies

# 令牌过期/缺失标志（命中则用 Set-Cookie 刷新 _m_h5_tk 后重试）
# 注意：闲鱼历史拼写为 EXOIRED，同时兼容标准拼写 EXPIRED 与 EMPTY（首次无令牌）
_TOKEN_EXPIRED_MARKERS = (
    "FAIL_SYS_TOKEN_EXOIRED",
    "FAIL_SYS_TOKEN_EXPIRED",
    "FAIL_SYS_TOKEN_EMPTY",
    "令牌过期",
    "令牌为空",
)

# 触发验证/被挤爆/机器检测等风控标志（命中则应切换账号重试）
_VALIDATE_MARKERS = (
    "FAIL_SYS_USER_VALIDATE",
    "RGV587",
    "FAIL_SYS_ILLEGAL_ACCESS",
    "FAIL_BIZ_WUA_IS_MACHINE",  # WUA机器检测（下单"无法购买哦"），换账号重试
    "WUA_IS_MACHINE",
    "哎哟喂",
    "挤爆",
    "punish",
    "captcha",
    "validate",
)

# 单次调用内最大尝试次数（令牌刷新/网络异常重试）
_MAX_ATTEMPTS = 3


async def fetch_proxy_from_api(api_url: str, account_id: str = "") -> Optional[str]:
    """调用代理 API 获取一个 HTTP 代理，返回 'http://host:port'，失败返回 None（直连）。

    参照系统设置中的代理使用方式：GET api_url，响应为纯文本 IP:PORT（多行时取第一非空行），
    严格解析 host:port 后拼成 http 代理 URL。失败（非200/空/格式异常/超时）统一返回 None。
    """
    if not api_url:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    logger.warning(f"【{account_id}】代理API返回状态码 {resp.status}，本次直连")
                    return None
                text = (await resp.text() or "").strip()
        if not text:
            logger.warning(f"【{account_id}】代理API返回内容为空，本次直连")
            return None
        # 取第一非空行（兼容多行返回的代理供应商）
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if not first_line:
            return None
        # 严格解析 host:port，避免误返回 HTML/JSON 被错误使用
        matched = re.match(r"^([^\s:]+):(\d{1,5})$", first_line)
        if not matched:
            logger.warning(f"【{account_id}】代理API返回格式无法解析: {first_line!r}，本次直连")
            return None
        host = matched.group(1)
        port = int(matched.group(2))
        if not (1 <= port <= 65535):
            logger.warning(f"【{account_id}】代理端口非法: {port}，本次直连")
            return None
        logger.info(f"【{account_id}】代理API获取成功: http://{host}:{port}")
        return f"http://{host}:{port}"
    except asyncio.TimeoutError:
        logger.warning(f"【{account_id}】代理API调用超时（10s），本次直连")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"【{account_id}】代理API调用异常: {exc}，本次直连")
        return None


async def mtop_call(
    account_id: str,
    cookies_str: str,
    api: str,
    version: str,
    data: dict,
    *,
    owner_id: Optional[int] = None,
    extra_params: Optional[Dict[str, str]] = None,
    proxy: Optional[str] = None,
) -> Dict[str, Any]:
    """调用闲鱼 mtop 接口，统一处理令牌过期/Session过期/风控。

    Args:
        proxy: 代理地址URL（http://host:port 或 socks5://user:pass@host:port），空则直连。

    Returns:
        {
          success: bool,
          account_invalid: bool,   # True 表示需切换账号（Session过期/验证/挤爆）
          res: dict|None,          # 接口原始返回 JSON
          error: str,
          cookies_str: str,        # 可能因令牌刷新而更新，调用方应回写实例并用于后续请求
        }
    """
    current_cookies = cookies_str
    token_refreshed = False
    last_error = ""
    url = f"https://h5api.m.goofish.com/h5/{api}/{version}/"

    for attempt in range(_MAX_ATTEMPTS):
        try:
            cookies = trans_cookies(current_cookies)
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False, "account_invalid": True, "res": None,
                "error": f"Cookie解析失败: {exc}", "cookies_str": current_cookies,
            }

        token = cookies.get("_m_h5_tk", "").split("_")[0] if cookies.get("_m_h5_tk") else ""
        t = str(int(time.time()) * 1000)
        data_val = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        sign = generate_sign(t, token, data_val)

        params = {
            "jsv": "2.7.2",
            "appKey": "34839810",
            "t": t,
            "sign": sign,
            "v": version,
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": api,
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.item.0.0",
        }
        if extra_params:
            params.update(extra_params)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.goofish.com",
            "Referer": "https://www.goofish.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Cookie": current_cookies,
        }

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 代理为 HTTP 代理（来自代理API的 http://host:port），aiohttp 原生支持，无需额外依赖
                async with session.post(
                    url, params=params, data={"data": data_val}, headers=headers, proxy=proxy or None
                ) as resp:
                    res_json = await resp.json(content_type=None)
                    set_cookies = extract_cookies_from_response(resp)
        except Exception as exc:  # noqa: BLE001
            last_error = f"请求异常: {exc}"
            logger.warning(f"【{account_id}】{api} {last_error}")
            await asyncio.sleep(0.5)
            continue

        ret = res_json.get("ret") or [""]
        ret_msg = ret[0] if ret else ""

        if "SUCCESS::" in ret_msg:
            # 期间刷新过令牌：把最新 Cookie 写回数据库
            if token_refreshed:
                await update_account_cookies_in_db(account_id, current_cookies, owner_id=owner_id)
                logger.info(f"【{account_id}】{api} 令牌已刷新并更新到数据库")
            return {"success": True, "account_invalid": False, "res": res_json, "error": "", "cookies_str": current_cookies}

        # 令牌过期/缺失：从 Set-Cookie 取新 _m_h5_tk 重签重试
        if any(marker in ret_msg for marker in _TOKEN_EXPIRED_MARKERS):
            if set_cookies:
                current_cookies = merge_cookies(current_cookies, set_cookies)
                token_refreshed = True
                logger.info(f"【{account_id}】{api} 令牌过期，已从 Set-Cookie 刷新 {len(set_cookies)} 个字段，重试")
            else:
                logger.warning(f"【{account_id}】{api} 令牌过期但响应无 Set-Cookie，重试")
            last_error = ret_msg
            await asyncio.sleep(0.3)
            continue

        # Session 过期：冷却 + 触发后台密码登录 + 切换账号
        if is_session_expired_error(ret):
            mark_account_session_expired(account_id)
            trigger_password_login_async(account_id)
            return {
                "success": False, "account_invalid": True, "res": res_json,
                "error": ret_msg or "Session过期", "cookies_str": current_cookies,
            }

        # 触发验证/被挤爆等风控：切换账号
        if any(marker in ret_msg for marker in _VALIDATE_MARKERS):
            return {
                "success": False, "account_invalid": True, "res": res_json,
                "error": ret_msg or "触发验证/风控", "cookies_str": current_cookies,
            }

        # 其他业务失败（商品下架/不可买等），不影响账号
        return {
            "success": False, "account_invalid": False, "res": res_json,
            "error": ret_msg or "调用失败", "cookies_str": current_cookies,
        }

    # 尝试次数耗尽（令牌刷新仍失败或网络异常）
    return {
        "success": False, "account_invalid": False, "res": None,
        "error": last_error or "调用失败，重试次数过多", "cookies_str": current_cookies,
    }


__all__ = ["mtop_call", "fetch_proxy_from_api"]
