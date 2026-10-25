"""公开查询四个服务的存活状态和真实 WebSocket 在线账号数量。"""
from __future__ import annotations

import asyncio

from loguru import logger

from app.core.config import get_settings
from app.services.service_status_service import get_backend_services_status, health_url, probe_health
from common.utils.internal_auth import build_internal_auth_headers
from common.utils.time_utils import get_beijing_now


async def _get_online_accounts() -> int | None:
    """查询真实连接数量，不返回账号明细；失败时返回 None 并保留明确错误反馈。"""
    settings = get_settings()
    try:
        result = await probe_health(
            f"{settings.websocket_service_url.rstrip('/')}/internal/accounts/connection-stats",
            headers=build_internal_auth_headers(settings.internal_api_token), include_data=True,
        )
        data = result.get("data")
        if not result["online"] or not isinstance(data, dict):
            return None
        count = data.get("connected")
        if type(count) is not int or count < 0:
            raise ValueError("消息服务返回的在线账号数量无效")
        return count
    except Exception:
        logger.exception("[公开状态] 获取真实在线账号数量失败")
        return None


async def get_public_status() -> dict:
    """并行查询四个服务和在线数量，返回公开字段及北京时间采集时间。

    Returns:
        四服务存活状态、在线账号数（不可获取时为 None）及数量查询说明。
    """
    backend_services, frontend, online_accounts = await asyncio.gather(
        get_backend_services_status(), probe_health(health_url("frontend")), _get_online_accounts(),
    )
    services = [{"key": "frontend", "label": "前端服务", "online": frontend["online"]}]
    services.extend({"key": item["key"], "label": item["label"], "online": item["online"]} for item in backend_services)
    return {
        "services": services,
        "online_accounts": online_accounts,
        "online_accounts_available": online_accounts is not None,
        "online_accounts_message": "查询成功" if online_accounts is not None else "在线账号数量暂不可用，请稍后重试",
        "checked_at": get_beijing_now().isoformat(),
    }
