"""
WebSocket 服务滑块调用客户端。

功能：
1. 调用 WebSocket 内部过滑块接口
2. 为浏览器排队和执行预留足够超时时间
3. 统一返回可供调度任务处理的业务响应
"""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from loguru import logger

from common.services.captcha.remote_timeout import get_remote_solve_timeout


async def solve_captcha_via_websocket(
    websocket_service_url: str,
    *,
    account_id: str,
    url: str,
    cookies: str,
    device_id: str,
    browser_timeout: int = 40,
) -> dict[str, Any]:
    """调用 WebSocket 内部接口完成滑块验证。

    Args:
        websocket_service_url: WebSocket 服务地址。
        account_id: 账号业务 ID。
        url: Token 接口返回的 punish 验证链接。
        cookies: 当前账号 Cookie，用于验证链接过期时重取链接。
        device_id: 当前 Token 缓存使用的设备 ID。
        browser_timeout: 单次浏览器滑块处理超时时间。

    Returns:
        WebSocket 服务的 JSON 响应；网络异常时返回 ``success=False``。
    """
    endpoint = f"{websocket_service_url.rstrip('/')}/internal/captcha/solve"
    timeout_seconds = get_remote_solve_timeout(browser_timeout)
    payload = {
        "account_id": account_id,
        "url": url,
        "browser_timeout": int(browser_timeout),
        "call_type": "local",
        "cookies": cookies,
        "device_id": device_id,
    }
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(endpoint, json=payload) as response:
                result = await response.json(content_type=None)
                if isinstance(result, dict):
                    return result
                return {
                    "success": False,
                    "message": "过滑块服务返回格式异常",
                    "data": None,
                }
    except asyncio.TimeoutError:
        logger.error(
            f"【{account_id}】调用WebSocket过滑块超时: {timeout_seconds:.0f}秒"
        )
        return {
            "success": False,
            "message": f"过滑块服务等待超时（{timeout_seconds:.0f}秒）",
            "data": None,
        }
    except aiohttp.ClientError as exc:
        logger.error(f"【{account_id}】调用WebSocket过滑块失败: {exc}")
        return {
            "success": False,
            "message": f"无法连接过滑块服务: {exc}",
            "data": None,
        }
    except Exception as exc:
        logger.error(f"【{account_id}】调用WebSocket过滑块异常: {exc}")
        return {
            "success": False,
            "message": f"过滑块失败: {exc}",
            "data": None,
        }
