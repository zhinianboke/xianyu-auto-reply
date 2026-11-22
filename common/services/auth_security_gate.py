"""认证 IP 安全入口：封禁提示优先，同时保留现有 Redis 计数和故障日志。"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from common.services.auth_security_policy import AuthIPRejected, enforce_ip_policy
from common.utils.async_cleanup import complete_before_cancellation

CountResult = TypeVar('CountResult')


async def check_ip_before_auth(
    session: AsyncSession, ip: str | None, count_attempt: Callable[[], Awaitable[CountResult]],
) -> CountResult:
    """先读取当前 IP 策略再执行计数；封禁时超限或 Redis 故障都不能覆盖禁止提示。

    Args:
        session: 当前请求数据库会话，策略即时生效。
        ip: 公共 client_ip 返回的合法 IP 或 None。
        count_attempt: 原入口的限流操作，封禁请求也执行，不另建连接池。
    Returns:
        非封禁时返回限流结果；封禁时完成计数尝试后抛原业务拒绝。
    """
    rejection = None
    policy_error = None
    try:
        await enforce_ip_policy(session, ip)
    except AuthIPRejected as exc:
        rejection = exc
    except Exception as exc:  # noqa: BLE001 - 策略读取失败仍计入尝试，但绝不放行认证
        policy_error = exc
    try:
        if rejection is not None:
            result = await complete_before_cancellation(
                count_attempt(), operation=f'封禁IP认证计数：client_ip={ip}',
            )
        else:
            result = await count_attempt()
    except asyncio.CancelledError as exc:
        if rejection is None:
            raise
        rejection.cancellation = exc
    except Exception as exc:  # 封禁请求计数故障完整记录，不改变封禁提示
        if rejection is None and policy_error is None:
            raise
        logger.opt(exception=exc).error('认证策略拒绝后的计数失败：client_ip={} reason={}', ip, str(rejection or policy_error))
    else:
        if rejection is None and policy_error is None:
            return result
    raise rejection or policy_error
