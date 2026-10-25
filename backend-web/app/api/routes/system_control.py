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

from fastapi import APIRouter, Depends
from loguru import logger

from app.api.deps import get_current_admin_user
from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.services.service_status_service import get_backend_services_status
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.service_restart import (
    SERVICE_META,
    detect_runtime,
    restart_service,
)

router = APIRouter(prefix="/system-control", tags=["系统管理"])

settings = get_settings()

_SERVICE_URL_MAP = {
    "websocket": lambda: settings.websocket_service_url,
    "scheduler": lambda: settings.scheduler_service_url,
}


@router.get("/status")
async def get_services_status(
    _admin: User = Depends(get_current_admin_user),
) -> ApiResponse:
    """
    查询三个服务的在线状态

    统一通过调用各服务的健康检查接口判断（而非仅检测端口占用），
    能真实反映 HTTP 服务是否可响应：
    - backend-web：/api/v1/health/ping
    - websocket：/health/ping，同时返回账号后台启动说明
    - scheduler：/health
    三个探测并行执行，单个超时 5 秒且不重试。
    """
    runtime = detect_runtime()
    services = await get_backend_services_status()
    return ApiResponse(
        success=True,
        message="查询成功",
        data={"runtime": runtime, "services": services},
    )


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
