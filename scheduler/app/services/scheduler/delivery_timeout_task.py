"""
自动发货消息超时检测任务

功能：
1. 扫描 send_status='unknown' 且 created_at 超过 5 分钟的自动发货日志
2. 将这些记录的 send_status 更新为 'timeout'

该任务定期清理因 WebSocket 发送后未收到服务端响应而滞留在 unknown 状态的记录，
避免发送状态长期显示为"未知"，同时不影响正在等待响应的最新记录。
"""
from __future__ import annotations

from datetime import timedelta

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.auto_reply_message_log import XYAutoReplyMessageLog
from common.utils.time_utils import get_beijing_now


class DeliveryTimeoutTask:
    """自动发货消息超时检测任务"""

    # 超过该时间阈值的 unknown 记录将被标记为 timeout
    TIMEOUT_MINUTES = 5
    # 单批更新上限：避免一次长事务锁住大量日志行，导致实时日志 INSERT 锁等待超时
    BATCH_SIZE = 500

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
        # created_at 全链路按北京时间存储（server_default=func.now()，MySQL 会话时区为 +08:00），
        # 因此阈值也必须用北京时间（naive），否则与 UTC 比较会相差 8 小时导致超时判定严重滞后。
        threshold = get_beijing_now().replace(tzinfo=None) - timedelta(minutes=self.TIMEOUT_MINUTES)

        total = 0
        while True:
            id_stmt = (
                select(XYAutoReplyMessageLog.id)
                .where(
                    XYAutoReplyMessageLog.send_status == "unknown",
                    XYAutoReplyMessageLog.reply_strategy == "auto_delivery",
                    XYAutoReplyMessageLog.created_at < threshold,
                )
                .order_by(XYAutoReplyMessageLog.id)
                .limit(self.BATCH_SIZE)
            )
            log_ids = list((await session.execute(id_stmt)).scalars().all())
            if not log_ids:
                break

            update_stmt = (
                update(XYAutoReplyMessageLog)
                .where(
                    XYAutoReplyMessageLog.id.in_(log_ids),
                    XYAutoReplyMessageLog.send_status == "unknown",
                    XYAutoReplyMessageLog.reply_strategy == "auto_delivery",
                    XYAutoReplyMessageLog.created_at < threshold,
                )
                .values(send_status="timeout")
            )
            result = await session.execute(update_stmt)
            await session.commit()
            updated = max(int(result.rowcount or 0), 0)
            total += updated

            # 并发回写已改变状态时，本批可能全部不匹配。此时重新查询仍可能拿到
            # 相同 ID，必须退出，避免形成无进展的循环。
            if updated == 0 or len(log_ids) < self.BATCH_SIZE:
                break

        if total > 0:
            logger.info(f"[发货超时检测] 已将 {total} 条 unknown 记录标记为 timeout")
        return total


# 模块级单例，供调度器引用
delivery_timeout_task_service = DeliveryTimeoutTask()
