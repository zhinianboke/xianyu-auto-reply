"""主系统和推广后台共用登录流程：失败计数、账号锁定与事务内审计。"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session_recovery import rollback_session
from common.models.user import User, UserRole
from common.schemas.auth import LoginRequest, LoginResponse
from common.services.auth_rate_limit_service import (
    AuthRateLimitRejected,
    begin_login_attempt,
    extend_login_attempt,
    finish_login_attempt,
)
from common.services.auth_security_gate import check_ip_before_auth
from common.services.auth_security_policy import AuthIPRejected
from common.services.email_domain_policy import (
    EmailDomainRejected,
    enforce_email_domain,
)
from common.services.email_verification_code_service import check_email_code
from common.services.user_auth_service import (
    UserAuthenticationRejected,
    UserAuthService,
)
from common.services.user_login_log_service import (
    LOGIN_METHOD_EMAIL_CODE,
    LOGIN_METHOD_EMAIL_PASSWORD,
    LOGIN_METHOD_USERNAME_PASSWORD,
    UserLoginLogService,
)
from common.utils.async_cleanup import complete_before_cancellation


class LoginRejected(ValueError):
    """登录资料、验证码等业务条件不满足。"""

    code = 40001


def login_identity(payload: LoginRequest | Mapping) -> tuple[str, str, str | None]:
    """提取登录方式和可识别身份；畸形值不转换为虚构账号。"""
    values = payload.model_dump() if isinstance(payload, LoginRequest) else payload
    username, email = values.get('username'), values.get('email')
    username = username if isinstance(username, str) else ''
    email = email if isinstance(email, str) else None
    if username and values.get('password'):
        # 用户名入口不采用调用方额外填写的邮箱，避免成功清掉无关邮箱的失败计数。
        return LOGIN_METHOD_USERNAME_PASSWORD, username, None
    if email:
        method = LOGIN_METHOD_EMAIL_PASSWORD if values.get('password') else LOGIN_METHOD_EMAIL_CODE
        return method, email, email
    return LOGIN_METHOD_USERNAME_PASSWORD, username, None


def _audit_account(account: str) -> str | None:
    """保留可入库账号快照；无法编码或超出字段长度的原值由请求日志完整保留。"""
    if len(account) > 255 or any(0xD800 <= ord(c) <= 0xDFFF for c in account):
        return None
    return account


async def perform_login(
    payload: LoginRequest | Mapping, ip: str | None, auth_service: UserAuthService,
    session: AsyncSession, login_log_service: UserLoginLogService, *,
    captcha_check: Callable[[str], tuple[bool, str]],
    settings_loader: Callable[[AsyncSession], Awaitable[Mapping[str, str]]],
    validation_message: str | None = None,
    supported_login_methods: frozenset[str] | None = None,
) -> LoginResponse:
    """登录并完成计数和审计；参数拒绝也走同一收尾，不发令牌或消费验证码。

    成功清零、最后登录时间和成功日志在同一数据库事务提交；Redis先保存
    本次失败候选，事务成功后才清零，基础设施故障不降级放行。
    """
    method, account, requested_email = login_identity(payload)
    values = payload.model_dump() if isinstance(payload, LoginRequest) else payload
    user_id, attempt = None, None
    authenticated, needs_recovery = False, False
    ip_rejected = False
    message, code = '登录失败', 40001
    cancellation = None
    try:
        # 查库前占位；查库失败和非法参数同样计入 IP / 原始身份次数。
        async def reserve_attempt():
            """为本次请求保存原占位，IP拒绝后仍可持久化失败候选。"""
            nonlocal attempt
            attempt = await begin_login_attempt(ip, account, requested_email)
            return attempt

        await check_ip_before_auth(session, ip, reserve_attempt)
        user = None
        if account and _audit_account(account) is not None:
            user = await auth_service.find_login_user(account, by_email=method != LOGIN_METHOD_USERNAME_PASSWORD)
        if user is not None:
            user_id = user.id
            # 有效锁必须在任何密码/验证码认证前检查，三种方式共用同一状态。
            user = await auth_service.lock_login_user(user)
            attempt = await extend_login_attempt(attempt, user.username, user.email)
        if validation_message:
            raise LoginRejected(validation_message)
        if supported_login_methods is not None and method not in supported_login_methods:
            raise LoginRejected('推广后台仅支持用户名和密码登录')
        email = (user.email if user else None) if method == LOGIN_METHOD_USERNAME_PASSWORD else requested_email
        if email:
            await enforce_email_domain(session, email, bound_email=user.email if user else None)
        if method in {LOGIN_METHOD_USERNAME_PASSWORD, LOGIN_METHOD_EMAIL_PASSWORD}:
            password = values.get('password')
            if not account or not password:
                raise LoginRejected('请提供有效的登录信息')
            settings = await settings_loader(session)
            if settings.get('login_captcha_enabled') in (None, 'true', '1'):
                challenge = values.get('geetest_challenge')
                if not challenge:
                    raise LoginRejected('请完成滑动验证')
                verified, captcha_message = captcha_check(challenge)
                if not verified:
                    raise LoginRejected(captcha_message)
            if user is None or not auth_service._verify_user_password(user, password):
                raise LoginRejected('邮箱或密码错误' if method == LOGIN_METHOD_EMAIL_PASSWORD else '用户名或密码错误')
        elif requested_email and values.get('verification_code'):
            verified, code_message = check_email_code(requested_email, values['verification_code'], 'login')
            if not verified:
                raise LoginRejected(code_message)
            if user is None:
                raise LoginRejected('该邮箱未注册')
        else:
            raise LoginRejected('请提供有效的登录信息')
        authenticated = True
        message, code = '登录成功', 200
    except (AuthIPRejected, EmailDomainRejected, AuthRateLimitRejected, UserAuthenticationRejected, LoginRejected) as exc:
        message, code = str(exc), exc.code
        ip_rejected = isinstance(exc, AuthIPRejected)
        if ip_rejected:
            cancellation = exc.cancellation
    except asyncio.CancelledError as exc:
        cancellation = exc
        message, code = '登录请求已取消，请重新登录', 50001
        needs_recovery = True
        logger.warning('登录请求已取消：account={} client_ip={}', account, ip)
    except Exception as exc:  # noqa: BLE001 - 认证边界记录完整异常并完成失败计数和审计
        logger.opt(exception=exc).error('登录处理失败：account={} client_ip={}', account, ip)
        message, code = '登录服务暂不可用，请稍后重试', 50001
        needs_recovery = True

    async def write_failure(
        reason: str, business_code: int, session_ready: bool, *, count_user: bool = True,
        audit_reason: str | None = None,
    ) -> LoginResponse:
        """连续失败与失败审计一起提交；损坏会话改用独立审计保留真实拒绝原因。"""
        try:
            failure_user_id = user_id
            if session_ready and failure_user_id is None and account and _audit_account(account) is not None:
                # Redis入口超限或早期查询异常也属于登录失败，仍识别账号用于共用锁计数。
                failure_user = await auth_service.find_login_user(
                    account, by_email=method != LOGIN_METHOD_USERNAME_PASSWORD,
                )
                failure_user_id = failure_user.id if failure_user is not None else None
            if session_ready and failure_user_id is not None and count_user:
                failure_hint = await auth_service.record_login_failure(User(id=failure_user_id))
                if audit_reason is None and reason in {'用户名或密码错误', '邮箱或密码错误'}:
                    reason = f'{reason}，{failure_hint}'
            await login_log_service.record(
                login_method=method, success=False, owner_id=None,
                login_account=_audit_account(account), client_ip=ip, result_message=audit_reason or reason,
                strict=True, isolated=not session_ready,
            )
        except Exception as exc:  # noqa: BLE001 - 审计故障恢复会话后使用独立事务
            logger.opt(exception=exc).error('登录失败审计提交失败：account={} client_ip={}', account, ip)
            await rollback_session(session, operation='登录失败审计')
            audit_saved = False
            try:
                await login_log_service.record(
                    login_method=method, success=False, owner_id=None,
                    login_account=_audit_account(account), client_ip=ip, result_message=audit_reason or reason,
                    strict=True, isolated=True,
                )
                audit_saved = True
            except Exception as audit_exc:  # noqa: BLE001 - 独立审计故障必须明确记录并拒绝
                logger.opt(exception=audit_exc).error('独立登录失败审计也失败：account={} client_ip={}', account, ip)
            recovery_message = ('登录失败结果保存异常，已补记登录日志，请联系管理员' if audit_saved
                                else '登录日志记录失败，请稍后重试')
            return LoginResponse(
                success=False, code=business_code if ip_rejected else 50001,
                message=f'{message}；{recovery_message}' if ip_rejected else recovery_message, data=None,
            )
        return LoginResponse(success=False, code=business_code, message=reason, data=None)

    async def finalize() -> LoginResponse:
        """保留失败候选、事务提交认证结果与审计，最后清理成功请求的 Redis 计数。"""
        nonlocal user_id, attempt
        success, final_message, final_code = authenticated, message, code
        audit_reason = None
        success_snapshot = None
        session_ready = not needs_recovery or await rollback_session(session, operation='登录处理收尾')
        if ip_rejected and session_ready and account and _audit_account(account) is not None:
            try:
                # IP拒绝不认证凭据；只补齐已存在账号的哈希身份，三种方式共享失败额度。
                rejected_user = await auth_service.find_login_user(
                    account, by_email=method != LOGIN_METHOD_USERNAME_PASSWORD,
                )
                if rejected_user is not None:
                    user_id = rejected_user.id
                    if attempt is not None:
                        attempt = await extend_login_attempt(attempt, rejected_user.username, rejected_user.email)
            except Exception as exc:  # noqa: BLE001 - 封禁提示优先，识别和计数故障仍完整记录
                logger.opt(exception=exc).error('封禁IP登录失败身份补齐失败：account={} client_ip={}', account, ip)
                session_ready = await rollback_session(session, operation='封禁IP登录身份补齐')
        if attempt:
            try:
                success_snapshot = await finish_login_attempt(attempt, success=False, prepare_success=success)
            except Exception as exc:  # noqa: BLE001 - Redis故障不放行，保留拒绝原因
                logger.opt(exception=exc).error('登录限流计数保存失败：account={} client_ip={}', account, ip)
                success = False
                audit_reason = final_message if not authenticated else None
                if not ip_rejected:
                    final_message = f'{final_message}；登录频率计数保存失败，请稍后重试' if not authenticated else '登录频率校验暂不可用，请稍后重试'
                    final_code = 50001
        if success and session_ready:
            commit_started = False
            try:
                current = await auth_service.reset_login_failure(User(id=user_id))
                response = LoginResponse(
                    success=True, code=200, message='登录成功',
                    token=auth_service.create_access_token(current),
                    refresh_token=auth_service.create_refresh_token(current),
                    user_id=current.id, username=current.username,
                    is_admin=current.role == UserRole.ADMIN, account_limit=current.account_limit,
                )
                await login_log_service.record(
                    login_method=method, success=True, owner_id=user_id,
                    login_account=_audit_account(account), client_ip=ip, result_message='登录成功',
                    strict=True, commit=False,
                )
                commit_started = True
                await session.commit()
            except Exception as exc:  # noqa: BLE001 - 成功事务故障回滚，不推测提交结果
                logger.opt(exception=exc).error('登录成功事务提交失败：account={} client_ip={}', account, ip)
                session_ready = await rollback_session(session, operation='登录成功事务')
                success = False
                if isinstance(exc, UserAuthenticationRejected):
                    final_message, final_code = str(exc), exc.code
                else:
                    final_message = '登录结果暂无法确认，请稍后重试' if commit_started else '登录结果保存失败，请稍后重试'
                    final_code = 50001
                if commit_started:
                    # 提交结果不确定时，不能重复加账号计数或推测数据库提交结果。
                    return await write_failure(final_message, final_code, session_ready, count_user=False)
            else:
                try:
                    await finish_login_attempt(attempt, success=True, snapshot=success_snapshot)
                except Exception as exc:  # noqa: BLE001 - 已提交成功的清理故障显式告警
                    logger.opt(exception=exc).error('登录已提交，Redis失败计数清理失败：account={} client_ip={}', account, ip)
                    # 真实认证已经提交成功，保留安全计数并显式报告清理故障，不能虚报失败。
                    response.message = '登录成功，但频率计数清理失败，请联系管理员'
                return response
        return await write_failure(final_message, final_code, session_ready, audit_reason=audit_reason)

    result = await complete_before_cancellation(finalize(), operation=f'登录收尾：account={account} client_ip={ip}')
    if cancellation:
        raise cancellation
    return result
