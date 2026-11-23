"""统一独立审计事务：准备回调重新取锁，明确未提交最多三次，提交未知禁止重试。"""
from __future__ import annotations

import asyncio
import traceback
from collections.abc import Awaitable, Callable

from loguru import logger
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.services.registration_log_service import database_error_code, known_uncommitted
from common.utils.file_log_sink import consume_file_log_failures, record_file_log_failure


class AuditWriteError(RuntimeError):
    """审计持久化失败，区分已知未提交和无法判断的提交结果。"""

    def __init__(self, message: str, *, commit_unknown: bool = False):
        """保存面向用户的中文原因及禁止重试标记。"""
        super().__init__(message)
        self.commit_unknown = commit_unknown


def report_safely(message: str, exception: BaseException | None = None, *, level: str = 'ERROR') -> str | None:
    """输出完整错误；日志输出故障作为显式返回值，不阻断后续数据库审计。"""
    try:
        logger.opt(exception=exception).log(level, message)
        logger.complete()
    except Exception as exc:
        record_file_log_failure(''.join(traceback.format_exception(exc)))
    return consume_file_log_failures()


class AuditWriter:
    """统一会话工厂独立事务写入器，允许准备回调锁定和更新同一事务的调度状态。"""

    def __init__(self, session_factory=None):
        """默认复用全局工厂；隔离验证可以注入测试会话，不创建引擎。"""
        self.session_factory = session_factory or async_session_maker

    async def write(self, write: Callable[[AsyncSession], Awaitable], *, prepare=None,
                    context: str | Callable[[], str] = ''):
        """先prepare、再write、flush和commit；返回真实回调结果，取消仍传播。"""
        for attempt in range(1, 4):
            committing = committed = False
            original_error = None
            result = None
            try:
                async with self.session_factory() as session:
                    try:
                        if prepare:
                            await prepare(session)
                        result = await write(session)
                        await session.flush()
                        committing = True
                        await session.commit()
                        committed = True
                    except BaseException as exc:
                        original_error = exc
                        raise
            except BaseException as close_error:
                failure = original_error if original_error is not None else close_error
                file_errors = []
                # 执行中详情会增长，提交故障必须记录当前完整上下文，不能只保留扫描前快照。
                try:
                    current_context = context() if callable(context) else context
                except Exception as context_error:
                    # 日志上下文故障不能抹去COMMIT未知标记或触发相反的失败审计。
                    current_context = f'审计上下文读取失败：{type(context_error).__name__}: {context_error}'
                    file_error = report_safely(current_context, context_error)
                    if file_error:
                        file_errors.append(file_error)
                if original_error is not None and close_error is not original_error:
                    file_error = report_safely(f'审计事务会话关闭故障 context={current_context} '
                                              f'original_exception={type(original_error).__name__}: {original_error}', close_error)
                    if file_error:
                        file_errors.append(file_error)
                file_error = report_safely(f'独立审计事务故障 attempt={attempt} context={current_context} '
                              f'committing={committing} committed={committed} '
                              f'exception_type={type(failure).__name__} exception={failure}', failure)
                if file_error:
                    file_errors.append(file_error)
                if file_errors:
                    # 辅助故障输出也会排空缓冲，统一保留后再交给执行器报告，不能被下一条日志吃掉。
                    record_file_log_failure('; '.join(file_errors))
                if committed:
                    if not isinstance(close_error, Exception):
                        raise
                    raise AuditWriteError('审计已提交，但数据库会话关闭失败，请重新查询确认', commit_unknown=True) from close_error
                if not isinstance(failure, Exception):
                    raise failure
                retryable = known_uncommitted(failure) or (
                    not committing and isinstance(failure, DBAPIError)
                    and database_error_code(failure) in {2002, 2003, 2005}
                ) or (not committing and isinstance(failure, DBAPIError)
                      and 'database is locked' in str(failure.orig).lower())
                if retryable and attempt < 3:
                    await asyncio.sleep(attempt * 0.2)
                    continue
                raise AuditWriteError(
                    f'安全审计或调度状态保存失败：{type(failure).__name__}: {failure}',
                    commit_unknown=committing and not known_uncommitted(failure),
                ) from failure
            return result
