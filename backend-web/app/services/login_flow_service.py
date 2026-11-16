"""系统用户登录流程：统一后缀校验、Redis 限流、验证码消费与审计日志。"""
from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.geetest import check_geetest_verified
from app.services.auth import AuthService
from app.services.system_setting_service import SystemSettingService
from app.services.user_login_log_service import (
    LOGIN_METHOD_EMAIL_CODE, LOGIN_METHOD_EMAIL_PASSWORD,
    LOGIN_METHOD_USERNAME_PASSWORD, UserLoginLogService,
)
from common.models.user import User, UserRole, UserStatus
from common.db.session_recovery import rollback_session
from common.schemas.auth import LoginRequest, LoginResponse
from common.services.auth_rate_limit_service import (
    AuthRateLimitRejected, begin_login_attempt, finish_login_attempt,
)
from common.services.email_domain_policy import EmailDomainRejected, enforce_email_domain
from common.services.email_verification_code_service import check_email_code
from common.utils.async_cleanup import complete_before_cancellation


class LoginRejected(ValueError):
    """登录条件不满足时的业务错误。"""

    code = 40001


async def perform_login(
    payload: LoginRequest,
    ip: str | None,
    auth_service: AuthService,
    session: AsyncSession,
    login_log_service: UserLoginLogService,
) -> LoginResponse:
    """执行三种登录方式；参数为请求、IP 和现有服务，返回兼容旧客户端的登录响应。"""
    method = LOGIN_METHOD_USERNAME_PASSWORD
    if not (payload.username and payload.password) and payload.email:
        method = LOGIN_METHOD_EMAIL_PASSWORD if payload.password else LOGIN_METHOD_EMAIL_CODE
    account = payload.username if method == LOGIN_METHOD_USERNAME_PASSWORD else payload.email
    account = account or ''
    user: User | None = None
    attempt = None
    message = "登录失败"
    code = 40001
    authenticated = False
    owner_id = None
    response = None
    cancellation = None
    needs_recovery = False
    try:
        user = await auth_service.find_login_user(account, by_email=method != LOGIN_METHOD_USERNAME_PASSWORD)
        owner_id = user.id if user else None
        # 所有拒绝均在占用限流额度后执行；账号登录绑定邮箱与邮箱登录共用邮箱维度。
        attempt = await begin_login_attempt(
            ip, user.username if user else account, user.email if user else payload.email,
        )
        email = (user.email if user else None) if method == LOGIN_METHOD_USERNAME_PASSWORD else payload.email
        if email:
            await enforce_email_domain(session, email, bound_email=user.email if user else None)
        if method in {LOGIN_METHOD_USERNAME_PASSWORD, LOGIN_METHOD_EMAIL_PASSWORD} and payload.password:
            settings = await SystemSettingService(session).list_settings()
            if settings.get('login_captcha_enabled') in (None, 'true', '1'):
                if not payload.geetest_challenge:
                    raise LoginRejected("请完成滑动验证")
                verified, message = check_geetest_verified(payload.geetest_challenge)
                if not verified:
                    raise LoginRejected(message)
            if method == LOGIN_METHOD_USERNAME_PASSWORD:
                authenticated_user, message = await auth_service.authenticate_by_username(account, payload.password)
            else:
                authenticated_user, message = await auth_service.authenticate_by_email(account, payload.password)
            if not authenticated_user:
                raise LoginRejected(message or "登录失败")
            user = authenticated_user
        elif method == LOGIN_METHOD_EMAIL_CODE and payload.email and payload.verification_code:
            # 后缀已经检查，新策略拒绝时不会消费先前获取的验证码。
            verified, message = check_email_code(payload.email, payload.verification_code, 'login')
            if not verified:
                raise LoginRejected(message)
            if user is None:
                raise LoginRejected("该邮箱未注册")
        else:
            raise LoginRejected("请提供有效的登录信息")
        if user.status != UserStatus.ACTIVE:
            raise LoginRejected("账号已禁用，请联系管理员")
        response = LoginResponse(
            success=True, message="登录成功",
            token=auth_service.create_access_token(user),
            refresh_token=auth_service.create_refresh_token(user),
            user_id=user.id, username=user.username,
            is_admin=user.role == UserRole.ADMIN, account_limit=user.account_limit,
        )
        await auth_service.mark_login(user)
        authenticated = True
        message = "登录成功"
        code = 200
    except (EmailDomainRejected, AuthRateLimitRejected, LoginRejected) as exc:
        message, code = str(exc), exc.code
    except asyncio.CancelledError as exc:
        cancellation = exc
        message, code = "登录请求已取消，请重新登录", 50001
        logger.warning("登录请求已取消：account={} client_ip={}", account, ip)
        needs_recovery = True
    except Exception as exc:
        logger.opt(exception=exc).error("登录处理失败：account={} client_ip={}", account, ip)
        message, code = "登录服务暂不可用，请稍后重试", 50001
        needs_recovery = True

    async def finalize() -> LoginResponse:
        """按已确定的认证结果恢复会话、收尾限流并提交审计，返回统一登录响应。"""
        success, final_message, final_code = authenticated, message, code
        session_ready = True
        if needs_recovery:
            session_ready = await rollback_session(session, operation="登录处理收尾")
        if attempt:
            try:
                await finish_login_attempt(attempt, success=success)
            except Exception as exc:
                logger.opt(exception=exc).error("登录限流计数保存失败：account={} client_ip={}", account, ip)
                # 已拒绝的请求保留真实拒绝原因；只有原本成功的认证需要改为服务失败。
                if success:
                    success = False
                    final_message, final_code = "登录频率校验暂不可用，请稍后重试", 50001
        try:
            await login_log_service.record(
                login_method=method, success=success, owner_id=owner_id,
                login_account=account, client_ip=ip, result_message=final_message,
                strict=True, isolated=not session_ready,
            )
        except Exception as exc:
            logger.opt(exception=exc).error("登录审计提交失败：account={} client_ip={}", account, ip)
            return LoginResponse(success=False, code=50001, message="登录日志记录失败，请稍后重试")
        if not success:
            return LoginResponse(success=False, code=final_code, message=final_message, data=None)
        return response

    result = await complete_before_cancellation(
        finalize(), operation=f"登录收尾：account={account} client_ip={ip}",
    )
    if cancellation:
        raise cancellation
    return result
