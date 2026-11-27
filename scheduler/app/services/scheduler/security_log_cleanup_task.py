"""按北京时间分批清理安全日志表中超过保留期的记录。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import delete, or_, select

from common.db.retry import with_db_retry
from common.db.session import async_session_maker
from common.models.security_log import SecurityLog
from common.utils.async_cleanup import complete_before_cancellation
from common.utils.time_utils import get_beijing_now_naive

_RETENTION_DAYS = 20
_CLEANUP_INTERVAL_SECONDS = 60 * 60
_BATCH_SIZE = 500


@with_db_retry(retry_on_lock_contention=True)
async def _delete_expired_batch(cutoff: datetime) -> tuple[int, int]:
    """以开始时间或历史记录的结束时间判断是否过期，返回选取数和删除数。"""
    table = SecurityLog.__table__
    expired = table.c.started_at < cutoff
    expired_legacy = table.c.started_at.is_(None) & (table.c.finished_at < cutoff)
    commit_started = False
    deleted_count = None
    try:
        async with async_session_maker() as session:
            statement = (
                select(table.c.id)
                .where(expired)
                .order_by(table.c.started_at, table.c.id)
                .limit(_BATCH_SIZE)
            )
            ids = list(await session.scalars(statement))
            if len(ids) < _BATCH_SIZE:
                # 旧表自检补齐时间字段时保留空值；仅用已有结束时间判断这类记录是否过期。
                legacy_statement = (
                    select(table.c.id)
                    .where(expired_legacy)
                    .order_by(table.c.id)
                    .limit(_BATCH_SIZE - len(ids))
                )
                ids.extend(await session.scalars(legacy_statement))
            if not ids:
                return 0, 0
            result = await session.execute(
                delete(table).where(table.c.id.in_(ids), or_(expired, expired_legacy))
            )
            commit_started = True
            await session.commit()
            deleted_count = result.rowcount
            return len(ids), deleted_count
    except Exception as exc:
        # 在会话关闭后判断提交阶段，防止关闭异常覆盖提交状态并触发整批重试。
        if deleted_count is not None:
            raise RuntimeError(f"本批已删除 {deleted_count} 条安全日志，但数据库会话关闭失败") from exc
        if commit_started:
            raise RuntimeError("本批安全日志清理提交结果未确认") from exc
        raise


async def run_security_log_cleanup() -> None:
    """调度服务启动后清理一轮，此后每小时运行，单轮失败后记录堆栈。"""
    while True:
        cutoff = get_beijing_now_naive() - timedelta(days=_RETENTION_DAYS)
        deleted = 0
        try:
            while True:
                selected, removed = await complete_before_cancellation(
                    _delete_expired_batch(cutoff), operation="提交本批过期安全日志清理"
                )
                deleted += removed
                if selected < _BATCH_SIZE:
                    break
            logger.info("安全日志清理完成，截止时间={}，删除记录数={}", cutoff, deleted)
        except Exception:  # noqa: BLE001 -- 调度边界记录完整异常并继续下一轮。
            logger.exception("安全日志清理失败，截止时间={}，此前各批已确认删除记录数={}", cutoff, deleted)
        await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)
