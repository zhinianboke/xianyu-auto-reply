"""注册审计公共服务：只追加真实结果，注册发码与邮件日志同事务提交。"""
from __future__ import annotations

import asyncio
import json

from loguru import logger
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.email_log import XYEmailLog
from common.models.registration_log import RegistrationLog
from common.utils.time_utils import get_beijing_now_naive


class RegistrationAuditError(RuntimeError):
    """注册审计失败；提交结果未知时禁止重写或追加相反结果。"""

    def __init__(self, message: str, *, commit_unknown: bool = False):
        super().__init__(message)
        self.commit_unknown = commit_unknown


def audit_text(value: object) -> str | None:
    """保留原始审计字段；非法 JSON 类型序列化，无效 Unicode 用可读转义保留。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value.encode('utf-8', errors='backslashreplace').decode('utf-8')
    return json.dumps(value, ensure_ascii=True, default=str)


def database_error_code(exc: BaseException) -> int | None:
    """提取驱动明确的 MySQL 错误码，非数据库异常不推断事务结果。"""
    original = exc.orig if isinstance(exc, DBAPIError) else exc
    arguments = getattr(original, 'args', ())
    return arguments[0] if arguments and isinstance(arguments[0], int) else None


def known_uncommitted(exc: BaseException) -> bool:
    """只认定锁超时/死锁等数据库明确拒绝，连接中断不能推断 COMMIT 结果。"""
    return isinstance(exc, DBAPIError) and database_error_code(exc) in {1205, 1213}


async def append_registration_log(
    session: AsyncSession, *, username: object = None, email: object = None,
    operation: str, success: bool, ip: str | None, message: str,
    owner_id: int | None = None,
) -> RegistrationLog:
    """在调用方事务追加注册日志并 flush，不自行提交；参数为真实请求及结果。"""
    record = RegistrationLog(
        owner_id=owner_id, username=audit_text(username), email=audit_text(email),
        operation=operation, success=success, client_ip=ip,
        message=audit_text(message), created_at=get_beijing_now_naive(),
    )
    session.add(record)
    await session.flush()
    return record


async def save_registration_audit(
    *, username: object = None, email: object = None, operation: str,
    success: bool, ip: str | None, message: str, owner_id: int | None = None,
    email_operation: str | None = None, registration: bool = True,
) -> None:
    """用统一会话工厂提交独立审计，发码的两类记录同事务各一条。

    Args:
        username/email/operation/success/ip/message/owner_id: 真实请求来源与确定结果。
        email_operation: 发码时同时追加原邮件日志；不传则仅注册提交审计。
        registration: 仅明确注册用途为 True，未知用途不猜为注册。
    Returns:
        成功无返回值；失败抛出明确审计异常，提交未知时绝不盲目重试。
    """
    for attempt in range(1, 4):
        committing = False
        committed = False
        transaction_error: BaseException | None = None
        try:
            async with async_session_maker() as session:
                try:
                    if registration:
                        await append_registration_log(
                            session, username=username, email=email, operation=operation,
                            success=success, ip=ip, message=message, owner_id=owner_id,
                        )
                    if email_operation is not None:
                        session.add(XYEmailLog(
                            owner_id=owner_id, recipient_email=audit_text(email) or '',
                            trigger_operation=email_operation, success=success, client_ip=ip,
                            result_message=audit_text(message), created_at=get_beijing_now_naive(),
                        ))
                    await session.flush()
                    committing = True
                    await session.commit()
                    committed = True
                except BaseException as exc:  # 仅保存原事务/取消故障并原样抛出。
                    # 必须在进入 __aexit__ 前保存原故障；关闭异常不能改写提交是否未知。
                    transaction_error = exc
                    raise
        except BaseException as close_or_transaction_error:  # 关闭可覆盖取消，必须恢复原语义。
            if transaction_error is not None and transaction_error is not close_or_transaction_error:
                logger.opt(exception=close_or_transaction_error).error(
                    '注册审计会话关闭覆盖原异常：operation={} email={} client_ip={} '
                    'transaction_exception_type={} transaction_exception={}',
                    operation, email, ip, type(transaction_error).__name__, transaction_error,
                )
            failure = transaction_error if transaction_error is not None else close_or_transaction_error
            if committed:
                logger.opt(exception=close_or_transaction_error).error(
                    '注册审计已提交但会话关闭失败：operation={} email={} client_ip={}', operation, email, ip,
                )
                if not isinstance(close_or_transaction_error, Exception):
                    raise
                return
            # 取消和进程退出不得因会话关闭的普通异常被改写为可重试业务错误。
            if not isinstance(failure, Exception):
                raise failure
            if not isinstance(close_or_transaction_error, Exception):
                raise
            retryable = known_uncommitted(failure) or (
                not committing and isinstance(failure, DBAPIError)
                and database_error_code(failure) in {2002, 2003, 2005}
            )
            logger.opt(exception=failure).error(
                '注册审计保存失败：attempt={} operation={} username={} email={} owner_id={} '
                'client_ip={} success={} reason={} committing={}',
                attempt, operation, username, email, owner_id, ip, success, message, committing,
            )
            if retryable and attempt < 3:
                await asyncio.sleep(attempt * 0.2)
                continue
            raise RegistrationAuditError(
                '注册日志记录失败，请联系管理员' if registration else '邮件日志记录失败，请联系管理员',
                commit_unknown=committing and not known_uncommitted(failure),
            ) from failure
        else:
            # 只有提交和会话关闭都正常结束才走此分支；已提交后关闭故障在上方明确记录。
            return
