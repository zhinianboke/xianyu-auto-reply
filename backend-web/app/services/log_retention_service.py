"""
日志保留天数运行时刷新服务。

功能：
1. 刷新当前 backend-web 进程的日志保留策略
2. 通知 WebSocket 与 Scheduler 服务刷新
3. 返回需要自动同步兜底的服务状态
"""
from __future__ import annotations

from loguru import logger

from app.core.config import get_settings
from app.core.http_client import get_http_client
from common.utils.logging_utils import update_log_retention


async def _notify_service(service_name: str, service_url: str, retention_days: int) -> dict:
    """通过内部 HTTP 接口通知目标服务刷新日志保留天数。"""
    if not service_url:
        return {"success": False, "message": f"{service_name}服务地址未配置，将由自动同步任务补齐"}
    try:
        response = await get_http_client().post(
            f"{service_url.rstrip('/')}/internal/logs/retention",
            json={"retention_days": retention_days},
        )
        success = bool(response.get("success"))
        default_message = f"{service_name}服务刷新成功" if success else f"{service_name}服务刷新失败"
        return {"success": success, "message": str(response.get("message") or default_message)}
    except Exception as exc:  # noqa: BLE001 - 内部服务通知失败需兜底并交由自动同步任务补齐。
        logger.opt(exception=exc).error(
            f"通知{service_name}刷新日志保留天数失败: "
            f"retention_days={retention_days}, service_url={service_url}, "
            f"exception_type={type(exc).__name__}, exception={exc}"
        )
        return {
            "success": False,
            "message": f"{service_name}服务刷新失败: {type(exc).__name__}: {exc}，将由自动同步任务补齐",
        }


async def refresh_log_retention_runtime(retention_days: int) -> dict:
    """刷新当前服务并广播通知其它服务。"""
    settings = get_settings()
    local_updated = update_log_retention(retention_days)
    return {
        "backend_web": {
            "success": True,
            "message": "backend-web服务已刷新" if local_updated else "backend-web服务无需变更",
        },
        "websocket": await _notify_service("WebSocket", settings.websocket_service_url, retention_days),
        "scheduler": await _notify_service("Scheduler", settings.scheduler_service_url, retention_days),
        "promotion_backend": {
            "success": True,
            "message": "返佣服务将通过自动同步任务应用最新日志保留天数",
        },
    }
