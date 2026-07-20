"""
风控日志启动清理服务。

功能：
1. WebSocket 服务启动时结束上一次进程遗留的处理中日志
2. 保留历史数据，并记录服务重启导致任务中断的具体原因
3. 数据库操作失败时自动重试
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import update

from common.db.session import async_session_maker
from common.models.risk_control_log import XYRiskControlLog
from common.utils.time_utils import get_beijing_now_naive


WEBSOCKET_RESTART_RESULT = "WebSocket服务重启，原待处理风控任务已中断"
WEBSOCKET_RESTART_ERROR = "任务处理期间WebSocket服务发生重启，无法继续执行"


@dataclass(frozen=True, slots=True)
class RiskControlLogCleanupResult:
    """风控日志启动清理结果。"""

    success: bool
    updated_count: int = 0
    message: str = ""


async def fail_processing_risk_control_logs_on_restart(
    *,
    max_attempts: int = 3,
    retry_delay_seconds: float = 1.0,
) -> RiskControlLogCleanupResult:
    """将所有处理中风控日志标记为服务重启失败。

    Args:
        max_attempts: 数据库写入最大尝试次数。
        retry_delay_seconds: 相邻重试之间的等待秒数。
    Returns:
        成功时返回实际更新条数；重试耗尽后返回具体错误。
    """
    attempts = max(1, int(max_attempts))
    checked_at = get_beijing_now_naive()
    last_error = ""

    for attempt in range(1, attempts + 1):
        try:
            async with async_session_maker() as session:
                update_result = await session.execute(
                    update(XYRiskControlLog)
                    .where(XYRiskControlLog.processing_status == "processing")
                    .values(
                        processing_status="failed",
                        processing_result=WEBSOCKET_RESTART_RESULT,
                        error_message=WEBSOCKET_RESTART_ERROR,
                        updated_at=checked_at,
                    )
                )
                await session.commit()
                updated_count = int(update_result.rowcount or 0)
                return RiskControlLogCleanupResult(
                    True,
                    updated_count=updated_count,
                    message=(
                        f"已将 {updated_count} 条待处理风控日志标记为失败"
                        if updated_count
                        else "没有需要结束的待处理风控日志"
                    ),
                )
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                await asyncio.sleep(max(0.0, retry_delay_seconds))

    return RiskControlLogCleanupResult(
        False,
        message=f"待处理风控日志清理失败，已重试{attempts}次：{last_error}",
    )
