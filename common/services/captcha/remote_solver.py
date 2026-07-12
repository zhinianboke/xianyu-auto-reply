"""
远程过滑块 - 异步调用封装

功能：
1. 以 async httpx 调用远程过滑块接口，避免在异步管理器里直调同步 requests 阻塞事件循环
2. 与 orchestrator._call_remote_solve 保持相同的请求协议与返回语义

对外入口：async solve_remote(...) -> (status, cookies)
    status: 'ok'（通过，cookies 为 x5*）/ 'fail'（有返回但未通过）/
            'url_expired'（验证链接已过期，调用方应刷新URL后重试）/
            'fallback'（超时或网络不可用，应回退本机逻辑）
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

import httpx
from loguru import logger


async def solve_remote(
    remote_url: str,
    remote_secret: str,
    user_id: str,
    url: str,
    browser_timeout: int = 40,
    cookies_str: str = "",
    device_id: str = "",
) -> Tuple[str, Optional[Dict[str, str]]]:
    """
    异步调用远程过滑块接口

    Args:
        remote_url: 远程过滑块服务地址
        remote_secret: 远程调用秘钥
        user_id: 账号/用户标识（仅用于日志与远程侧隔离）
        url: punish 验证链接
        browser_timeout: 远程单次浏览器超时（秒）
        cookies_str: 可选账号 Cookie（开启"传递Cookie"时传入），链接过期时远程可凭此重取
        device_id: 可选设备 ID，配合 cookies_str 供远程重取 token 使用
    Returns:
        (status, cookies)
    """
    payload: Dict[str, object] = {
        "secret_key": remote_secret,
        "account_id": str(user_id),
        "url": url,
        "browser_timeout": int(browser_timeout),
    }
    # 仅在开启"传递Cookie"开关时携带账号 Cookie / 设备 ID（默认不传，保护账号隐私）
    if cookies_str:
        payload["cookies"] = cookies_str
        payload["device_id"] = device_id or ""

    # 连接 8s 内必须建立，读取给足远程求解时间；超时/连不上 → 回退本机
    timeout = httpx.Timeout(max(90, int(browser_timeout) + 60), connect=8.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(remote_url, json=payload)
    except httpx.HTTPError as e:
        logger.warning(f"【{user_id}】远程过滑块超时/不可用，回退本机逻辑: {e}")
        return "fallback", None

    try:
        data = resp.json()
    except Exception as e:
        # 远程有响应但响应体异常：视为远程未通过（非超时 → 不回退）
        logger.warning(f"【{user_id}】远程过滑块响应解析失败，判失败（不回退）: {e}")
        return "fail", None

    if isinstance(data, dict) and data.get("success"):
        cookies = (data.get("data") or {}).get("cookies") or {}
        if cookies:
            return "ok", cookies
    # 远程明确反馈"验证链接已过期"：调用方需刷新URL后重试
    if isinstance(data, dict) and (data.get("data") or {}).get("url_expired"):
        logger.info(f"【{user_id}】远程反馈验证链接已过期(url_expired)")
        return "url_expired", None
    return "fail", None
