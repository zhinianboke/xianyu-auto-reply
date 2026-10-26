"""公开查询服务存活、真实在线账号数量及仪表盘口径的全局用户与账号总数。"""
from __future__ import annotations

import asyncio

from loguru import logger

from app.core.config import get_settings
from app.services.dashboard_totals_service import get_dashboard_totals
from app.services.service_status_service import HEALTH_PROBE_TIMEOUT, get_backend_services_status, health_url, probe_health
from common.db.retry import with_db_retry
from common.db.session import async_session_maker
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


@with_db_retry(max_retries=1, initial_delay=0.2)
async def _query_dashboard_totals() -> dict[str, int]:
    """使用统一会话工厂读取总数，连接失败重试时新建会话。

    Returns:
        实时用户和账号总数；数据库错误由调用方提供明确反馈。
    """
    async with async_session_maker() as session:
        return await get_dashboard_totals(session)


async def _get_dashboard_totals() -> dict[str, int] | None:
    """限时查询全局总数，包含重试最多五秒，失败返回 None。

    Returns:
        全局总数；超时或查询失败返回 None，不以零代替失败结果。
    """
    try:
        async with asyncio.timeout(HEALTH_PROBE_TIMEOUT):
            return await _query_dashboard_totals()
    except Exception:
        logger.exception("[公开状态] 获取全局用户与账号总数失败")
        return None


async def get_public_status() -> dict:
    """并行查询四服务、在线数量和全局总数，返回公开字段及北京时间。

    Returns:
        四服务存活状态、在线账号数、用户与账号总数及各数量查询说明。
    """
    backend_services, frontend, online_accounts, totals = await asyncio.gather(
        get_backend_services_status(), probe_health(health_url("frontend")), _get_online_accounts(),
        _get_dashboard_totals(),
    )
    services = [{"key": "frontend", "label": "前端服务", "online": frontend["online"]}]
    services.extend({"key": item["key"], "label": item["label"], "online": item["online"]} for item in backend_services)
    return {
        "services": services,
        "online_accounts": online_accounts,
        "online_accounts_available": online_accounts is not None,
        "online_accounts_message": "查询成功" if online_accounts is not None else "在线账号数量暂不可用，请稍后重试",
        "total_users": totals["total_users"] if totals is not None else None,
        "total_accounts": totals["total_accounts"] if totals is not None else None,
        "totals_available": totals is not None,
        "totals_message": "查询成功" if totals is not None else "用户和账号总数暂不可用，请稍后重试",
        "checked_at": get_beijing_now().isoformat(),
    }
