"""公共服务存活探测，供管理端和公开状态接口复用。"""
from __future__ import annotations

import asyncio
import json

import aiohttp
from loguru import logger

from app.core.config import get_settings
from common.utils.service_restart import SERVICE_META

HEALTH_PROBE_TIMEOUT = 5.0


def health_url(service_key: str) -> str:
    """根据服务标识构建存活检查地址，WebSocket 使用无需数据库的轻量检查。"""
    settings = get_settings()
    if service_key == "backend-web":
        return f"http://127.0.0.1:{settings.service_port}/api/v1/health/ping"
    if service_key == "frontend":
        return f"{settings.frontend_service_url.rstrip('/')}/frontend-health"
    if service_key == "websocket":
        return f"{settings.websocket_service_url.rstrip('/')}/health/ping"
    if service_key == "scheduler":
        return f"{settings.scheduler_service_url.rstrip('/')}/health"
    raise ValueError(f"未知服务：{service_key}")


async def probe_health(
    url: str, *, headers: dict | None = None, include_data: bool = False,
) -> dict:
    """单次请求探测服务存活，五秒超时；可供内部调用读取成功响应的数据。

    Args:
        url: 服务检查地址。
        headers: 内部接口鉴权请求头。
        include_data: 是否返回成功响应的 data，仅供服务层使用。
    Returns:
        是否在线、状态说明、是否正在初始化及可选响应数据。
    """
    timeout = aiohttp.ClientTimeout(total=HEALTH_PROBE_TIMEOUT)
    request_context = {"method": "GET", "url": url, "query": {}, "headers": headers or {}, "body": None}
    response_context = None
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                request_context.update(
                    url=str(resp.url), query=dict(resp.url.query),
                    headers=dict(resp.request_info.headers),
                )
                response_text = await resp.text()
                response_context = {"status": resp.status, "headers": dict(resp.headers), "body": response_text}
                payload = json.loads(response_text)
                online = resp.status < 400 and payload.get("success") is True
                if not online:
                    logger.error("[服务状态] 健康检查失败：request={} response={}", request_context, response_context)
                data = payload.get("data") or {}
                startup = data.get("account_startup") or {}
                result = {
                    "online": online,
                    "message": startup.get("message") or payload.get("message") or "",
                    "initializing": startup.get("status") == "starting",
                }
                if include_data:
                    result["data"] = data if online else None
                return result
    except Exception as exc:
        logger.exception("[服务状态] 健康检查请求失败：request={} response={}", request_context, response_context)
        message = (
            f"服务状态探测超时（{HEALTH_PROBE_TIMEOUT:g} 秒）"
            if isinstance(exc, asyncio.TimeoutError) else f"服务状态探测失败：{exc}"
        )
        result = {"online": False, "message": message, "initializing": False}
        if include_data:
            result["data"] = None
        return result


async def get_backend_services_status() -> list[dict]:
    """并行获取三个后端服务状态，保留管理端现有服务标识和端口字段。"""
    keys = list(SERVICE_META)
    results = await asyncio.gather(*(probe_health(health_url(key)) for key in keys))
    return [
        {"key": key, "label": SERVICE_META[key]["label"], "port": SERVICE_META[key]["port"], **result}
        for key, result in zip(keys, results)
    ]
