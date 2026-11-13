"""
高德所在地查询的公共 HTTP 传输。

功能：
1. 为网页与定时任务提供独立于 app 包的高德请求入口；
2. 保留原 HTTP 客户端的三次尝试与指数退避，查询总超时由调用方控制；
3. 请求结束或取消时关闭连接，失败时完整记录请求、响应和异常。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urlencode

import aiohttp
from loguru import logger


HTTP_TIMEOUT_SECONDS = 30
HTTP_MAX_ATTEMPTS = 3
HTTP_RETRY_DELAY_SECONDS = 1.0


async def request_inputtips(
    url: str,
    *,
    params: dict[str, str],
    headers: dict[str, str],
) -> Any:
    """发送高德 GET 请求，网络错误与服务器错误沿用原重试规则。

    Args:
        url: 高德 inputtips 接口地址。
        params: 本次查询的完整参数。
        headers: 闲鱼网页 SDK 使用的请求头。
    Returns:
        Any: 原始 JSON 响应；非 JSON 响应保留在 text 字段中供业务层拒绝。
    Raises:
        aiohttp.ClientError: 三次请求均失败时抛出最后一次异常。
        asyncio.TimeoutError: HTTP 超时，或调用方的查询总超时到期。
    """
    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(HTTP_MAX_ATTEMPTS):
            request_detail: dict[str, Any] = {
                "method": "GET",
                "url": f"{url}{'&' if '?' in url else '?'}{urlencode(params)}",
                "query": params,
                "headers": headers,
                "body": None,
            }
            response_detail: dict[str, Any] = {
                "status": None, "headers": None, "body": None,
            }
            try:
                async with session.get(url, params=params, headers=headers) as response:
                    request_detail["url"] = str(response.request_info.real_url)
                    request_detail["headers"] = list(response.request_info.headers.items())
                    response_detail["status"] = response.status
                    response_detail["headers"] = list(response.headers.items())
                    response_detail["body"] = await response.text()
                    if response.status >= 500:
                        raise aiohttp.ClientError(
                            f"服务器错误 {response.status}: {response_detail['body']}"
                        )
                    try:
                        body = await response.json()
                    except (aiohttp.ContentTypeError, json.JSONDecodeError, UnicodeDecodeError):
                        body = {"text": response_detail["body"]}
                    if (
                        response.status >= 400
                        or not isinstance(body, dict)
                        or str(body.get("status")) != "1"
                    ):
                        logger.warning(
                            "高德所在地 HTTP 请求失败: operation=inputtips, result=failed, "
                            "request={}, response={}",
                            json.dumps(request_detail, ensure_ascii=False),
                            json.dumps(response_detail, ensure_ascii=False),
                        )
                    return body
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                final_attempt = attempt + 1 == HTTP_MAX_ATTEMPTS
                logger.opt(exception=exc).log(
                    "ERROR" if final_attempt else "WARNING",
                    "高德所在地请求异常: operation=inputtips, result=failed, "
                    "attempt={}/{}, request={}, response={}, exception_type={}, error={}",
                    attempt + 1,
                    HTTP_MAX_ATTEMPTS,
                    json.dumps(request_detail, ensure_ascii=False),
                    json.dumps(response_detail, ensure_ascii=False),
                    type(exc).__name__,
                    str(exc),
                )
                if final_attempt:
                    raise
                await asyncio.sleep(HTTP_RETRY_DELAY_SECONDS * (2 ** attempt))


__all__ = ["request_inputtips"]
