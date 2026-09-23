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

from common.core.config import get_settings
from common.services.captcha.remote_timeout import get_remote_solve_timeout
from common.utils.internal_auth import (
    build_internal_auth_headers,
    is_internal_api_url,
)


async def solve_captcha_via_websocket(
    websocket_service_url: str,
    *,
    account_id: str,
    account_row_id: int | None = None,
    token_cache_id: int | None = None,
    token_user_id: str = "",
    url: str,
    cookies: str,
    device_id: str,
    browser_timeout: int = 40,
) -> dict[str, Any]:
    """调用 WebSocket 内部接口完成滑块验证。

    Args:
        websocket_service_url: WebSocket 服务地址。
        account_id: 账号业务 ID。
        account_row_id: 可选账号数据库行 ID，供 WebSocket 端成功后精准写回 Cookie。
        token_cache_id: 可选 Token 缓存行 ID，供 WebSocket 端成功后写续期缓存。
        token_user_id: 可选 Token 缓存用户 ID，配合 token_cache_id 做条件更新。
        url: Token 接口返回的 punish 验证链接。
        cookies: 当前账号 Cookie，用于验证链接过期时重取链接。
        device_id: 当前 Token 缓存使用的设备 ID。
        browser_timeout: 单次浏览器滑块处理超时时间。

    Returns:
        WebSocket 服务的 JSON 响应；网络异常时返回 ``success=False``。
    """
    endpoint = f"{websocket_service_url.rstrip('/')}/internal/captcha/solve"
    if not is_internal_api_url(endpoint, (websocket_service_url,)):
        logger.error(f"【{account_id}】调用WebSocket过滑块失败：服务地址不合法")
        return {
            "success": False,
            "message": "WebSocket服务地址不合法",
            "data": None,
        }
    timeout_seconds = get_remote_solve_timeout(browser_timeout)
    payload = {
        "account_id": account_id,
        "url": url,
        "browser_timeout": int(browser_timeout),
        "call_type": "local",
        "cookies": cookies,
        "device_id": device_id,
    }
    if account_row_id is not None:
        payload["account_row_id"] = int(account_row_id)
    if token_cache_id is not None:
        payload["token_cache_id"] = int(token_cache_id)
        payload["token_user_id"] = token_user_id or ""
        payload["persist_token_cache"] = True
    request_not_sent_errors = (aiohttp.ClientConnectorError, aiohttp.InvalidURL)
    connection_timeout_error = getattr(aiohttp, "ConnectionTimeoutError", None)
    if connection_timeout_error is not None:
        request_not_sent_errors += (connection_timeout_error,)
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 启动流程会把共享令牌注入公共配置；在独立调用或测试环境尚未完成启动时，
            # 不在客户端提前抛异常，仍让服务端用统一的 401 业务响应拒绝请求。
            token = (get_settings().internal_api_token or "").strip()
            request_kwargs = {"json": payload}
            if token and is_internal_api_url(endpoint, (websocket_service_url,)):
                request_kwargs["headers"] = build_internal_auth_headers(token)
            async with session.post(endpoint, **request_kwargs) as response:
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
            "_request_status_unknown": True,
        }
    except request_not_sent_errors as exc:
        logger.error(f"【{account_id}】调用WebSocket过滑块失败: {exc}")
        return {
            "success": False,
            "message": f"无法连接过滑块服务: {exc}",
            "data": None,
        }
    except aiohttp.ClientError as exc:
        logger.error(f"【{account_id}】调用WebSocket过滑块连接中断: {exc}")
        return {
            "success": False,
            "message": f"过滑块服务连接中断: {exc}",
            "data": None,
            "_request_status_unknown": True,
        }
    except Exception as exc:
        logger.error(f"【{account_id}】调用WebSocket过滑块异常: {exc}")
        return {
            "success": False,
            "message": f"过滑块失败: {exc}",
            "data": None,
            "_request_status_unknown": True,
        }
