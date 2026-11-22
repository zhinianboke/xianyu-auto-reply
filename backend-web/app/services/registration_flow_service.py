"""注册提交公共流程：计数、当前安全规则、用户创建与完整事务审计。"""
from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy.exc import IntegrityError

from app.services.system_setting_service import SystemSettingService
from app.services.user_service import UserService
from common.db.session_recovery import rollback_session
from common.models.registration_log import REGISTRATION_OPERATION_SUBMIT
from common.schemas.common import ApiResponse
from common.schemas.user import UserCreate
from common.services.auth_rate_limit_service import (
    AuthRateLimitRejected,
    check_registration_limit,
)
from common.services.auth_security_gate import check_ip_before_auth
from common.services.auth_security_policy import AuthIPRejected
from common.services.email_domain_policy import (
    EmailDomainRejected,
    enforce_email_domain,
)
from common.services.email_verification_code_service import check_email_code
from common.services.registration_log_service import (
    RegistrationAuditError,
    append_registration_log,
    database_error_code,
    known_uncommitted,
    save_registration_audit,
)
from common.services.registration_policy import get_registration_rejection_message
from common.utils.async_cleanup import complete_before_cancellation


class RegistrationRejected(ValueError):
    """注册业务拒绝，统一收尾后返回原中文原因。"""

    def __init__(self, message: str, code: int = 40001):
        super().__init__(message)
        self.code = code


async def perform_registration(
    payload: UserCreate, ip: str | None, user_service: UserService,
    setting_service: SystemSettingService,
) -> ApiResponse:
    """提交注册；成功用户和审计同事务，失败回滚后独立保存真实失败结果。"""
    session = user_service.session
    owner_id, cancellation = None, None
    committing, committed, audit_stage = False, False, False
    failure_message, failure_code, detail = '注册失败，请稍后重试', 50001, None
    try:
        await check_ip_before_auth(session, ip, lambda: check_registration_limit(ip, payload.email))
        await enforce_email_domain(session, payload.email)
        rejection = get_registration_rejection_message(await setting_service.list_settings())
        if rejection:
            raise RegistrationRejected(rejection, 403)
        existing = await user_service.get_by_username(payload.username)
        if existing:
            owner_id = existing.id
            raise RegistrationRejected('用户名已被注册', 409)
        existing = await user_service.get_by_email(payload.email)
        if existing:
            owner_id = existing.id
            raise RegistrationRejected('邮箱已被注册', 409)
        if not payload.verification_code:
            raise RegistrationRejected('请输入邮箱验证码')
        valid, message = check_email_code(payload.email, payload.verification_code, 'register')
        if not valid:
            raise RegistrationRejected(message)
        user = await user_service.create(payload, commit=False)
        # 注册接口保留原响应契约、不自动登录；序列化必须在提交前完成。
        response = ApiResponse(success=True, code=200, message='注册成功', data=None)
        response.model_dump(mode='json')
        audit_stage = True
        await append_registration_log(
            session, username=payload.username, email=payload.email,
            operation=REGISTRATION_OPERATION_SUBMIT, success=True, ip=ip,
            message='注册成功', owner_id=user.id,
        )
        committing = True
        await session.commit()
        committed = True
        return response
    except (AuthIPRejected, EmailDomainRejected, AuthRateLimitRejected, RegistrationRejected) as exc:
        failure_message, failure_code = str(exc), exc.code
        if isinstance(exc, AuthIPRejected):
            cancellation = exc.cancellation
    except asyncio.CancelledError as exc:
        cancellation = exc
        failure_message = '注册请求已取消'
        logger.warning('注册请求已取消：username={} email={} client_ip={}', payload.username, payload.email, ip)
    except IntegrityError as exc:
        committing = False
        logger.opt(exception=exc).error('注册数据冲突：username={} email={} client_ip={}', payload.username, payload.email, ip)
        if not audit_stage and database_error_code(exc) == 1062:
            failure_message, failure_code = '用户名或邮箱已被注册', 409
        else:
            failure_message, failure_code = '注册日志记录失败，请联系管理员' if audit_stage else '注册失败，请稍后重试', 50001
        detail = f'{failure_message}：{type(exc).__name__}: {exc}'
    except Exception as exc:  # noqa: BLE001 - 系统异常也必须提交失败审计
        logger.opt(exception=exc).error('注册失败：username={} email={} client_ip={}', payload.username, payload.email, ip)
        failure_message = '注册日志记录失败，请联系管理员' if audit_stage else '注册失败，请稍后重试'
        detail = f'{failure_message}：{type(exc).__name__}: {exc}'
        if committing and not known_uncommitted(exc):
            # COMMIT 已发出但结果未知：不能补记可能与已成功用户相矛盾的失败日志。
            await complete_before_cancellation(rollback_session(session, operation='注册提交结果未知'), operation='注册连接恢复')
            return ApiResponse(success=False, code=50001, message='注册提交结果暂无法确认，请勿重复注册，请联系管理员核实', data=None)
        committing = False

    async def finish() -> ApiResponse:
        """仅恢复业务事务和保存拒绝审计，不继续执行被取消的注册。"""
        await rollback_session(session, operation='注册失败收尾')
        try:
            await save_registration_audit(
                username=payload.username, email=payload.email, operation=REGISTRATION_OPERATION_SUBMIT,
                success=False, ip=ip, message=detail or failure_message, owner_id=owner_id,
            )
        except RegistrationAuditError as exc:
            return ApiResponse(success=False, code=failure_code if failure_code == 40001 else 50001,
                               message=f'{failure_message}（{exc}）', data=None)
        return ApiResponse(success=False, code=failure_code, message=failure_message, data=None)

    if committing and not committed:
        # 取消也可能发生于提交期间，不追加矛盾失败记录。
        await complete_before_cancellation(rollback_session(session, operation='注册提交取消'), operation='注册连接恢复')
        if cancellation is not None:
            raise cancellation
        return ApiResponse(success=False, code=50001, message='注册提交结果暂无法确认，请联系管理员核实', data=None)
    result = await complete_before_cancellation(finish(), operation=f'注册审计收尾：email={payload.email} client_ip={ip}')
    if cancellation is not None:
        raise cancellation
    return result
