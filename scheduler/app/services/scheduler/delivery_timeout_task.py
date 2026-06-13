"""
自动发货消息超时检测任务

功能：
1. 扫描 send_status='unknown' 且 created_at 超过 5 分钟的自动发货日志
2. 将这些记录的 send_status 更新为 'timeout'

该任务定期清理因 WebSocket 发送后未收到服务端响应而滞留在 unknown 状态的记录，
避免发送状态长期显示为"未知"，同时不影响正在等待响应的最新记录。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.auto_reply_message_log import XYAutoReplyMessageLog


class DeliveryTimeoutTask:
    """自动发货消息超时检测任务"""

    # 超过该时间阈值的 unknown 记录将被标记为 timeout
    TIMEOUT_MINUTES = 5

    async def execute(self) -> str:
        """
        执行超时检测任务

        Returns:
            执行结果摘要
        """
        logger.info("[发货超时检测] 开始执行")
        try:
            async with async_session_maker() as session:
                count = await self._mark_unknown_as_timeout(session)
                summary = f"标记 {count} 条 unknown 记录为 timeout"
                logger.info(f"[发货超时检测] 执行完成: {summary}")
                return summary
        except Exception as e:
            logger.error(f"[发货超时检测] 执行异常: {e}")
            return f"执行异常: {e}"

    async def _mark_unknown_as_timeout(self, session: AsyncSession) -> int:
        """
        将超时的 unknown 记录更新为 timeout

        Args:
            session: 数据库会话

        Returns:
            更新的记录数
        """
        threshold = datetime.now(timezone.utc) - timedelta(minutes=self.TIMEOUT_MINUTES)

        stmt = (
            update(XYAutoReplyMessageLog)
            .where(
                XYAutoReplyMessageLog.send_status == "unknown",
                XYAutoReplyMessageLog.reply_strategy == "auto_delivery",
                XYAutoReplyMessageLog.created_at < threshold,
            )
            .values(send_status="timeout")
        )
        result = await session.execute(stmt)
        await session.commit()
        count = result.rowcount
        if count > 0:
            logger.info(f"[发货超时检测] 已将 {count} 条 unknown 记录标记为 timeout")
        return count


# 模块级单例，供调度器引用
delivery_timeout_task_service = DeliveryTimeoutTask()
