"""
系统管理 - 服务重启路由

功能：
1. 提供三个后端服务（后端服务 / 消息服务 / 定时任务服务）的重启接口
2. 提供三个服务的在线状态查询接口
3. 自动适配运行环境（docker / 打包 / 开发）：
   - 重启 backend-web（自身）：本机 restart_service（先返回响应再触发）
   - 重启 websocket / scheduler：
       docker  → HTTP 调用目标服务 /internal/system/self-restart 让其自杀，容器拉起
       dev/frozen → 本机 restart_service 直接杀端口并重新拉起

权限：仅管理员可操作。
"""
from __future__ import annotations

import asyncio

import aiohttp
from fastapi import APIRouter, Depends
from loguru import logger

from app.api.deps import get_current_admin_user
from app.core.config import get_settings
from app.core.http_client import get_http_client
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.service_restart import (
    SERVICE_META,
    detect_runtime,
    restart_service,
)

router = APIRouter(prefix="/system-control", tags=["系统管理"])

settings = get_settings()

# 探测服务在线状态的 HTTP 超时（秒）：无重试，避免离线服务拖慢状态查询
_HEALTH_PROBE_TIMEOUT = 30.0

# 三个服务对应的 HTTP 基址（用于 docker 环境远程触发自重启）
_SERVICE_URL_MAP = {
    "websocket": lambda: settings.websocket_service_url,
    "scheduler": lambda: settings.scheduler_service_url,
}


def _health_url(service_key: str) -> str:
    """
    构建各服务的健康检查 URL

    - backend-web：本机 127.0.0.1:<port>/api/v1/health/ping
    - websocket / scheduler：使用服务间通信地址 + /health（dev 为 localhost，docker 为容器名）
    """
    if service_key == "backend-web":
        return f"http://127.0.0.1:{settings.service_port}/api/v1/health/ping"
    base = _SERVICE_URL_MAP[service_key]().rstrip("/")
    return f"{base}/health"


@router.get("/status")
async def get_services_status(
    _admin: User = Depends(get_current_admin_user),
) -> ApiResponse:
    """
    查询三个服务的在线状态

    统一通过调用各服务的健康检查接口判断（而非仅检测端口占用），
    能真实反映 HTTP 服务是否可响应：
    - backend-web：/api/v1/health/ping
    - websocket / scheduler：/health
    三个探测并行执行，单个超时 15 秒且不重试。
    """
    runtime = detect_runtime()
    keys = list(SERVICE_META.keys())
    results = await asyncio.gather(*[_probe_health(_health_url(k)) for k in keys])
    services = []
    for key, online in zip(keys, results):
        meta = SERVICE_META[key]
        services.append({
            "key": key,
            "label": meta["label"],
            "port": meta["port"],
            "online": online,
        })
    return ApiResponse(
        success=True,
        message="查询成功",
        data={"runtime": runtime, "services": services},
    )


async def _probe_health(url: str) -> bool:
    """
    调用健康检查接口判断服务是否在线（单次请求，短超时，无重试）

    Args:
        url: 健康检查完整 URL

    Returns:
        True 表示服务 HTTP 可响应（HTTP 状态码 < 400）
    """
    timeout = aiohttp.ClientTimeout(total=_HEALTH_PROBE_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                return resp.status < 400
    except Exception:
        return False


@router.post("/restart/{service_key}")
async def restart(
    service_key: str,
    _admin: User = Depends(get_current_admin_user),
) -> ApiResponse:
    """
    重启指定服务

    Args:
        service_key: backend-web / websocket / scheduler

    Returns:
        统一响应；成功表示「已触发重启」，服务会在数秒内恢复。
    """
    if service_key not in SERVICE_META:
        return ApiResponse(success=False, message=f"未知服务：{service_key}", data=None)

    label = SERVICE_META[service_key]["label"]
    runtime = detect_runtime()

    # 重启 backend 自身：本机触发（内部会先返回响应再执行）
    if service_key == "backend-web":
        result = restart_service("backend-web")
        return ApiResponse(
            success=bool(result.get("success")),
            message=result.get("message") or "",
            data={"mode": result.get("mode")},
        )

    # 重启 websocket / scheduler
    if runtime == "docker":
        # docker：各服务独立容器，backend 无法直接杀其进程，
        # 改为 HTTP 通知目标服务自杀，容器 restart 策略拉起。
        ok, message = await _remote_self_restart(service_key)
        return ApiResponse(
            success=ok,
            message=message or (f"{label}正在重启" if ok else f"{label}重启失败"),
            data={"mode": runtime},
        )

    # dev / frozen：同机部署，本机直接杀端口并重新拉起
    result = restart_service(service_key)
    return ApiResponse(
        success=bool(result.get("success")),
        message=result.get("message") or "",
        data={"mode": result.get("mode")},
    )


async def _remote_self_restart(service_key: str) -> tuple[bool, str]:
    """
    通过 HTTP 通知目标服务重启自身（docker 环境）

    Args:
        service_key: websocket / scheduler

    Returns:
        (是否成功, 提示信息)
    """
    base_url = _SERVICE_URL_MAP[service_key]()
    url = f"{base_url}/internal/system/self-restart"
    try:
        http_client = get_http_client()
        response = await http_client.post(url)
        success = bool(response.get("success"))
        return success, response.get("message") or ""
    except Exception as e:
        logger.error(f"[系统管理] 通知 {service_key} 重启失败：{e}")
        return False, f"通知服务重启失败：{e}"
