"""
邮箱验证码发送与验证接口。

功能：
1. 按邮件用途检查账号及验证码发送频率
2. 注册验证码发送与验证遵循当前有效注册开关
3. 成功、失败与拒绝均调用公共邮件日志服务
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from loguru import logger
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.routes.geetest import check_geetest_verified
from app.services.email_service import send_verification_code_email
from app.services.system_setting_service import SystemSettingService
from app.services.user_service import UserService
from common.models.registration_log import REGISTRATION_OPERATION_CODE
from common.schemas.common import ApiResponse
from common.services.auth_rate_limit_service import (
    AuthRateLimitRejected,
    check_email_code_limit,
)
from common.services.auth_request_validation import AuthenticationAPIRoute
from common.services.auth_security_gate import check_ip_before_auth
from common.services.auth_security_policy import AuthIPRejected, enforce_ip_policy
from common.services.email_code_request_audit import (
    EMAIL_CODE_OPERATIONS,
    email_code_operation,
    reject_email_code_request,
)
from common.services.email_domain_policy import (
    EmailDomainRejected,
    enforce_email_domain,
)
from common.services.email_verification_code_service import (
    check_email_code,
    cleanup_expired_email_codes,
    email_code_store,
    generate_verification_code,
    invalidate_email_code,
)
from common.services.registration_log_service import (
    RegistrationAuditError,
    save_registration_audit,
)
from common.services.registration_policy import get_registration_rejection_message
from common.utils.async_cleanup import complete_before_cancellation
from common.utils.http_utils import get_client_ip

router = APIRouter(route_class=AuthenticationAPIRoute)


class SendCodeRequest(BaseModel):
    """发送邮箱验证码请求"""
    email: EmailStr
    session_id: Optional[str] = None
    type: str = "register"  # register, login 或 reset_password
    # 极验滑动验证参数（仅忘记密码 reset_password 场景使用，参照登录逻辑）
    geetest_challenge: Optional[str] = None
    geetest_validate: Optional[str] = None
    geetest_seccode: Optional[str] = None


class CodeRequestRejected(ValueError):
    """验证码请求的明确业务拒绝，统一由入口记录失败日志。"""

    def __init__(self, message: str, code: int = 40001):
        super().__init__(message)
        self.code = code


@router.post("/send-email-code")
async def send_email_verification_code(
    http_request: Request,
    request: SendCodeRequest,
    db: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """按当前规则发送验证码；参数为请求及会话，返回已记录审计结果的统一响应。"""
    http_request.state.email_code_started = True
    operations = EMAIL_CODE_OPERATIONS
    is_registration = 'type' in request.model_fields_set and request.type == 'register'
    client_ip = get_client_ip(http_request)
    owner_id = None
    pending_record = None
    cancellation = None
    needs_recovery = False
    rejection_detail = None
    ip_rejected = False
    send_outcome = None
    audit_completed = False

    async def reject(message: str, code: int = 40001, *, detail: str | None = None) -> ApiResponse:
        """提交本次拒绝的邮件日志后返回失败，日志不可用时明确提示用户。"""
        return await reject_email_code_request(
            db, email=request.email, purpose=request.type, ip=client_ip, message=message, code=code,
            owner_id=owner_id, recover_session=needs_recovery, detail=detail, preserve_code=ip_rejected,
            registration=is_registration,
        )

    async def audit_send(success: bool, message: str) -> None:
        """同事务记录已确定的发信结果；仅明确注册用途同时追加注册日志。"""
        await save_registration_audit(
            email=request.email, operation=REGISTRATION_OPERATION_CODE, success=success,
            ip=client_ip, message=message, owner_id=owner_id,
            email_operation=email_code_operation(request.type), registration=is_registration,
        )

    def pending_code_is_current() -> bool:
        """无参数，返回本次待发送验证码是否仍归当前请求所有且未过期。"""
        return (
            pending_record is not None
            and email_code_store.get(request.email) is pending_record
            and pending_record["expires_at"] > time.time()
        )

    try:
        count_type = request.type if request.type in operations else 'invalid'
        if request.type != 'reset_password':
            await check_ip_before_auth(
                db, client_ip, lambda: check_email_code_limit(client_ip, request.email, count_type),
            )
        else:
            await check_email_code_limit(client_ip, request.email, request.type)
        if request.type not in operations:
            raise CodeRequestRejected("验证码类型无效，请选择注册、登录或重置密码")
        existing_user = await UserService(db).get_by_email(request.email)
        owner_id = existing_user.id if existing_user else None
        # 被开关、后缀或其他条件拒绝的发信尝试也纳入频率限制。
        if request.type in {"register", "login"}:
            await enforce_email_domain(
                db, request.email,
                bound_email=existing_user.email if request.type == "login" and existing_user else None,
            )
        if request.type == "register":
            settings = await SystemSettingService(db).list_settings()
            message = get_registration_rejection_message(settings)
            if message:
                raise CodeRequestRejected(message, status.HTTP_403_FORBIDDEN)
            if existing_user:
                raise CodeRequestRejected("该邮箱已被注册")
        elif request.type == "reset_password":
            settings = await SystemSettingService(db).list_settings()
            if settings.get("login_captcha_enabled") in (None, "true", "1"):
                if not request.geetest_challenge:
                    raise CodeRequestRejected("请完成滑动验证")
                verified, message = check_geetest_verified(request.geetest_challenge)
                if not verified:
                    raise CodeRequestRejected(message)
        if request.type in {"login", "reset_password"} and not existing_user:
            raise CodeRequestRejected("该邮箱未注册")

        cleanup_expired_email_codes()
        stored = email_code_store.get(request.email)
        if stored and (stored.get("is_pending") or stored["expires_at"] - 240 > time.time()):
            raise CodeRequestRejected("验证码发送过于频繁，请稍后再试", 42901)
        code = generate_verification_code()
        pending_record = {
            "code": code, "type": request.type,
            "expires_at": time.time() + 300, "is_pending": True,
        }
        email_code_store[request.email] = pending_record
        # 邮件服务只报告真实结果；入口统一提交审计，避免后续拒绝重复记邮件日志。
        success, message = await send_verification_code_email(
            request.email, code, request.type, owner_id=owner_id, client_ip=client_ip,
            audit=False,
        )
        send_outcome = (success, message)
        if success and not pending_code_is_current():
            message = f'{message}；本次验证码已失效，请重新获取验证码'
            send_outcome = (success, message)
            await complete_before_cancellation(audit_send(success, message), operation='验证码已发送但失效审计')
            audit_completed = True
            return ApiResponse(success=False, code=40001, message='本次验证码已失效，请重新获取验证码', data=None)
        await complete_before_cancellation(audit_send(success, message), operation='验证码发送审计')
        audit_completed = True
        if not success:
            return ApiResponse(success=False, code=50001, message=message, data=None)
        if not pending_code_is_current():
            # 审计等待期间可能发生过期清理或后续请求替换；保留真实投递审计，不重复补记。
            logger.warning(
                "验证码已发送但审计完成时已失效：email={} type={} client_ip={}",
                request.email, request.type, client_ip,
            )
            return ApiResponse(success=False, code=40001, message='本次验证码已失效，请重新获取验证码', data=None)
        pending_record["expires_at"] = time.time() + 300
        pending_record["is_pending"] = False
        logger.info("发送邮箱验证码成功: email={} type={}", request.email, request.type)
        return ApiResponse(success=True, code=200, message="验证码已发送到您的邮箱，请查收", data=None)
    except RegistrationAuditError as exc:
        # 审计提交结果未知不能进入通用拒绝分支，避免重复或矛盾记录。
        logger.opt(exception=exc).error('验证码发送审计失败：email={} type={} client_ip={} outcome={}', request.email, request.type, client_ip, send_outcome)
        return ApiResponse(success=False, code=50001, message=f'{exc}，本次验证码已失效', data=None)
    except (AuthIPRejected, EmailDomainRejected, AuthRateLimitRejected, CodeRequestRejected) as exc:
        rejection_message, rejection_code = str(exc), exc.code
        if isinstance(exc, AuthIPRejected):
            # 用户识别放到受保护的收尾，查询故障不得跳过邮件审计或覆盖封禁提示。
            ip_rejected = True
            cancellation = exc.cancellation
    except asyncio.CancelledError as exc:
        cancellation = exc
        needs_recovery = True
        rejection_message, rejection_code = "验证码发送请求已取消，本次验证码已失效", 50001
        logger.warning("发送邮箱验证码已取消: email={} type={}", request.email, request.type)
        if send_outcome is not None:
            # 必要审计已经完成后传播的取消不再追加第二条失败记录。
            raise
    except Exception as exc:  # noqa: BLE001 - 发码故障记录完整异常并提交拒绝审计
        logger.opt(exception=exc).error(
            "发送邮箱验证码失败: email={} type={} client_ip={}", request.email, request.type, client_ip,
        )
        needs_recovery = True
        if audit_completed:
            # 真实投递审计已完成，后续异常不能追加相反结果。
            if pending_record is not None:
                invalidate_email_code(request.email, pending_record)
            return ApiResponse(success=False, code=50001, message='邮件已处理，但验证码状态异常，请重新获取验证码', data=None)
        rejection_message, rejection_code = "验证码发送失败，请稍后重试", 50001
        rejection_detail = f"发送邮箱验证码异常: {type(exc).__name__}: {exc}"
    finally:
        if pending_record is not None and pending_record.get("is_pending"):
            invalidate_email_code(request.email, pending_record)

    # 业务结果已确定；仅保护恢复与拒绝审计，不继续被取消的发信操作。
    result = await complete_before_cancellation(
        reject(rejection_message, rejection_code, detail=rejection_detail),
        operation=f"验证码拒绝收尾：email={request.email} type={request.type} client_ip={client_ip}",
    )
    if cancellation is not None:
        raise cancellation
    return result


@router.post("/verify-email-code")
async def verify_email_code(
    request: Request,
    email: str,
    code: str,
    code_type: str = "register",
    setting_service: SystemSettingService = Depends(deps.get_system_setting_service),
) -> ApiResponse:
    """验证并消费邮箱验证码；注册用途先检查当前开关。

    Args:
        email: 收件邮箱。
        code: 用户提交的验证码。
        code_type: 注册、登录或密码重置用途。
        setting_service: 读取当前注册开关的设置服务。
    Returns:
        统一校验响应；关闭注册时保留原验证码。
    """
    if code_type not in {"register", "login", "reset_password"}:
        return ApiResponse(success=False, message="验证码类型无效，请选择注册、登录或重置密码")
    if code_type in {"register", "login"}:
        ip = get_client_ip(request)
        try:
            await enforce_ip_policy(setting_service.session, ip)
            await enforce_email_domain(setting_service.session, email)
        except (AuthIPRejected, EmailDomainRejected) as exc:
            # 正常验证不能占发信的每分钟额度，否则刚发出的验证码会立即被挡。
            # 规则拒绝仍计现有验证码限流；仅消费校验并不触发发信，不伪造邮件日志。
            async def count_rejection():
                """在取消保护下计入拒绝尝试，频率故障不能覆盖安全策略提示。"""
                try:
                    await check_email_code_limit(ip, email, code_type)
                except AuthRateLimitRejected:
                    return
                except Exception as error:  # noqa: BLE001 - 拒绝已确定，完整记录计数故障
                    logger.opt(exception=error).error('验证码消费拒绝计数失败：client_ip={} email={} type={}', ip, email, code_type)

            await complete_before_cancellation(count_rejection(), operation=f'验证码消费拒绝计数：client_ip={ip}')
            return ApiResponse(success=False, code=exc.code, message=str(exc))
        except Exception as exc:  # noqa: BLE001 - 当前策略读取失败不得消费旧验证码
            logger.opt(exception=exc).error('验证码消费安全校验失败：client_ip={} email={} type={}', ip, email, code_type)
            return ApiResponse(success=False, code=50001, message='验证码安全校验暂不可用，请稍后重试')
    if code_type == "register":
        settings = await setting_service.list_settings()
        rejection_message = get_registration_rejection_message(settings)
        if rejection_message:
            return ApiResponse(
                success=False,
                code=status.HTTP_403_FORBIDDEN,
                message=rejection_message,
            )
    code_valid, message = check_email_code(email, code, code_type)
    return ApiResponse(success=code_valid, message=message)
