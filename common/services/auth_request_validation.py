"""认证参数异常收尾：登录、注册及验证码发信的模型拒绝也计数并审计。"""
from __future__ import annotations

import asyncio
import json

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from loguru import logger

from common.db.session import async_session_maker
from common.db.session_recovery import rollback_session
from common.models.registration_log import REGISTRATION_OPERATION_SUBMIT
from common.schemas.common import ApiResponse
from common.services.auth_rate_limit_service import (
    AuthRateLimitRejected,
    check_email_code_limit,
    check_registration_limit,
)
from common.services.auth_security_gate import check_ip_before_auth
from common.services.auth_security_policy import AuthIPRejected
from common.services.email_code_request_audit import (
    email_code_operation,
    reject_email_code_request,
)
from common.services.login_flow_service import perform_login
from common.services.login_settings_service import load_login_settings
from common.services.registration_log_service import (
    RegistrationAuditError,
    save_registration_audit,
)
from common.services.user_auth_service import UserAuthService
from common.services.user_login_log_service import UserLoginLogService
from common.utils.async_cleanup import complete_before_cancellation
from common.utils.http_utils import get_client_ip


def validation_message(exc: RequestValidationError, operation: str) -> str:
    """将参数错误映射为中文，避免向用户直接返回框架英文错误。"""
    labels = {'username': '用户名', 'email': '邮箱', 'password': '密码',
              'verification_code': '邮箱验证码', 'phone': '手机号',
              'geetest_challenge': '滑动验证码'}
    fields = list(dict.fromkeys(
        labels.get(str(error['loc'][-1]), '请求内容') for error in exc.errors() if error.get('loc')
    ))
    return f"{operation}参数格式不正确，请检查{'、'.join(fields) or '请求内容'}"


def cached_request_body(request: Request) -> object:
    """只解析请求已读取的缓存，返回已知原参数或 None，取消后不再等待网络请求体。"""
    if hasattr(request, '_json'):
        return request._json
    body = getattr(request, '_body', None)
    if body is None:
        return None
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        # 不解析不完整或非法 JSON，不根据部分文本推测验证码用途。
        return None


async def _reject_registration(values: dict, ip: str | None, message: str) -> ApiResponse:
    """注册模型/依赖拒绝仍计数，独立记录真实失败，不消费验证码或创建账号。"""
    code, owner_id, cancellation = 40001, None, None
    counted, ip_rejected = False, False

    async def count_attempt():
        """标记唯一计数调用，数据库会话不可用也尝试原统一 Redis 限流。"""
        nonlocal counted
        counted = True
        await check_registration_limit(ip, values.get('email'))

    try:
        async with async_session_maker() as session:
            try:
                await check_ip_before_auth(session, ip, count_attempt)
            except (AuthIPRejected, AuthRateLimitRejected) as exc:
                message, code = str(exc), exc.code
                if isinstance(exc, AuthIPRejected):
                    ip_rejected = True
                    cancellation = exc.cancellation
            except Exception as exc:  # noqa: BLE001 - 故障拒绝且保留完整上下文
                logger.opt(exception=exc).error('注册参数拒绝校验失败：client_ip={} body={}', ip, values)
                message, code = '注册校验暂不可用，请稍后重试', 50001
            session_ready = await rollback_session(session, operation='注册参数拒绝')
            for key in ('username', 'email'):
                if not session_ready:
                    break
                identity = values.get(key)
                if not isinstance(identity, str) or not identity or len(identity) > 255:
                    continue
                try:
                    user = await UserAuthService(session).find_login_user(identity, by_email=key == 'email')
                    if user is not None:
                        owner_id = user.id
                        break
                except Exception as exc:  # noqa: BLE001 - 识别失败不能跳过独立审计
                    logger.opt(exception=exc).error('注册拒绝用户识别失败：body={} client_ip={}', values, ip)
                    session_ready = await rollback_session(session, operation='注册拒绝用户识别')
    except Exception as exc:  # noqa: BLE001 - 依赖会话不可用仍由统一工厂独立审计
        logger.opt(exception=exc).error('注册拒绝会话不可用：body={} client_ip={}', values, ip)
        if not ip_rejected:
            code, message = 50001, '注册校验暂不可用，请稍后重试'
    if not counted:
        try:
            await count_attempt()
        except AuthRateLimitRejected as exc:
            if not ip_rejected:
                code, message = exc.code, str(exc)
        except Exception as exc:  # noqa: BLE001 - 依赖失败仍记录计数故障，不跳过审计
            logger.opt(exception=exc).error('注册拒绝补计数失败：body={} client_ip={}', values, ip)
    try:
        await save_registration_audit(
            username=values.get('username'), email=values.get('email'),
            operation=REGISTRATION_OPERATION_SUBMIT, success=False, ip=ip,
            message=message, owner_id=owner_id,
        )
    except RegistrationAuditError as exc:
        message = f'{message}（{exc}）'
        if code != 40001:
            code = 50001
    if cancellation is not None:
        raise cancellation
    return ApiResponse(success=False, code=code, message=message, data=None)


async def _reject_email_code(values: dict, ip: str | None, message: str) -> ApiResponse:
    """畸形发码请求先计数后落邮件失败日志，未知用途不假记找回密码。"""
    email, purpose = values.get('email'), values.get('type')
    progress = {}
    try:
        return await _reject_email_code_with_session(values, ip, message, progress)
    except Exception as exc:
        logger.opt(exception=exc).error('验证码参数拒绝会话不可用：body={} client_ip={}', values, ip)
        if progress.get('started'):
            if progress.get('cancellation') is not None:
                raise progress['cancellation'] from exc
            return progress.get('response') or ApiResponse(
                success=False, code=50001, message='验证码日志记录失败，请联系管理员', data=None,
            )
        count_purpose = purpose if isinstance(purpose, str) and purpose in {'register', 'login', 'reset_password'} else 'invalid'
        if not progress.get('counted'):
            try:
                await check_email_code_limit(ip, email, count_purpose)
            except AuthRateLimitRejected as error:
                message = str(error)
            except Exception as error:  # noqa: BLE001 - 会话不可用不跳过拒绝计数
                logger.opt(exception=error).error('验证码参数拒绝补计数失败：body={} client_ip={}', values, ip)
        try:
            await save_registration_audit(
                email=email, operation='register_code', registration=purpose == 'register',
                success=False, ip=ip, message=message,
                email_operation=email_code_operation(purpose),
            )
        except RegistrationAuditError as error:
            return ApiResponse(success=False, code=50001, message=f'{message}（{error}）', data=None)
        return ApiResponse(success=False, code=50001, message=message, data=None)


async def _reject_email_code_with_session(values: dict, ip: str | None, message: str, progress: dict) -> ApiResponse:
    """使用隔离会话计数并识别用户；审计一旦开始，异常不得触发外层重写。"""
    email, purpose = values.get('email'), values.get('type')
    count_purpose = purpose if isinstance(purpose, str) and purpose in {'register', 'login', 'reset_password'} else 'invalid'
    cancellation, ip_rejected, recover = None, False, False
    code = 40001
    async with async_session_maker() as session:
        try:
            async def count():
                """记录此请求已调用原发码计数，外层故障不得重复计数。"""
                progress['counted'] = True
                await check_email_code_limit(ip, email, count_purpose)
            if count_purpose != 'reset_password':
                await check_ip_before_auth(session, ip, count)
            else:
                await count()
        except (AuthIPRejected, AuthRateLimitRejected) as exc:
            message, code = str(exc), exc.code
            if isinstance(exc, AuthIPRejected):
                ip_rejected, cancellation = True, exc.cancellation
        except Exception as exc:  # noqa: BLE001 - 发信参数拒绝的配置或计数故障必须审计
            logger.opt(exception=exc).error('验证码参数拒绝校验失败：client_ip={} body={}', ip, values)
            message, code, recover = '验证码发送校验暂不可用，请稍后重试', 50001, True
        try:
            progress['started'] = True
            progress['cancellation'] = cancellation
            response = await reject_email_code_request(
                session, email=email, purpose=purpose, ip=ip, message=message, code=code,
                recover_session=recover, preserve_code=ip_rejected,
            )
        except Exception as exc:  # noqa: BLE001 - 不确定是否已审计时禁止外层重写
            logger.opt(exception=exc).error('验证码参数拒绝审计收尾失败：body={} client_ip={}', values, ip)
            response = ApiResponse(success=False, code=50001, message='验证码日志记录失败，请联系管理员', data=None)
        progress['response'] = response
    if cancellation is not None:
        raise cancellation
    return response


class AuthenticationAPIRoute(APIRoute):
    """只拦截认证和发码参数拒绝，保留 typed payload、OpenAPI 和其他接口行为。"""

    def get_route_handler(self):
        """包装原路由，异常请求先提交计数/审计，再返回统一 HTTP 200 业务响应。"""
        original = super().get_route_handler()

        async def handler(request: Request):
            """调用正常路由或收尾登录/注册的参数错误。"""
            try:
                return await original(request)
            except (Exception, asyncio.CancelledError) as exc:
                action = self.path.rsplit('/', 1)[-1]
                if request.method != 'POST' or action not in {'login', 'register', 'send-email-code'}:
                    raise
                if not isinstance(exc, RequestValidationError) and action == 'login':
                    raise
                if getattr(request.state, 'registration_started', False) or getattr(request.state, 'email_code_started', False):
                    # 已进入公共业务流程由其负责一次审计，不在外层盲目重写。
                    raise
                cancellation = exc if isinstance(exc, asyncio.CancelledError) else None
                if isinstance(exc, RequestValidationError):
                    rejected_body = exc.body
                elif cancellation is not None:
                    rejected_body = cached_request_body(request)
                else:
                    try:
                        rejected_body = await request.json()
                    except asyncio.CancelledError as body_cancellation:
                        cancellation = body_cancellation
                        rejected_body = cached_request_body(request)
                    except Exception:  # noqa: BLE001 - 非法JSON无可识别字段，不猜发码用途
                        rejected_body = None
                values = rejected_body if isinstance(rejected_body, dict) else {}
                ip = get_client_ip(request)
                operation = {'login': '登录', 'register': '注册', 'send-email-code': '发送验证码'}[action]
                message = validation_message(exc, operation) if isinstance(exc, RequestValidationError) else f'{operation}请求处理失败，请稍后重试'
                if cancellation is not None:
                    message = f'{operation}请求已取消'
                elif isinstance(exc, HTTPException) and isinstance(exc.detail, str):
                    message = exc.detail
                logger.opt(exception=exc).error('认证入口拒绝：path={} client_ip={} body={}', request.url.path, ip, rejected_body)

                async def finalize():
                    """独立事务只记录拒绝，不发令牌、消费验证码或创建用户。"""
                    if action == 'login':
                        async with async_session_maker() as session:
                            return await perform_login(
                                values, ip, UserAuthService(session), session, UserLoginLogService(session),
                                captcha_check=lambda _: (False, '参数错误'),
                                settings_loader=load_login_settings, validation_message=message,
                            )
                    if action == 'send-email-code':
                        return await _reject_email_code(values, ip, message)
                    return await _reject_registration(values, ip, message)

                response = await complete_before_cancellation(finalize(), operation=f'认证参数拒绝：{request.url.path}')
                if cancellation is not None:
                    raise cancellation
                return JSONResponse(status_code=200, content=response.model_dump())

        return handler
