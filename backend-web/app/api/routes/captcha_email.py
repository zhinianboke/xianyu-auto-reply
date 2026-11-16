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
from common.db.session_recovery import rollback_session
from common.schemas.common import ApiResponse
from common.services.email_log_service import (
    EMAIL_OPERATION_EMAIL_LOGIN_VERIFICATION_CODE,
    EMAIL_OPERATION_REGISTER_VERIFICATION_CODE,
    EMAIL_OPERATION_RESET_PASSWORD_VERIFICATION_CODE,
    record_email_log,
)
from common.services.email_verification_code_service import (
    check_email_code,
    cleanup_expired_email_codes,
    email_code_store,
    generate_verification_code,
    invalidate_email_code,
)
from common.services.auth_rate_limit_service import AuthRateLimitRejected, check_email_code_limit
from common.services.email_domain_policy import EmailDomainRejected, enforce_email_domain
from common.services.registration_policy import get_registration_rejection_message
from common.utils.async_cleanup import complete_before_cancellation
from common.utils.http_utils import get_client_ip

router = APIRouter()


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
    operations = {
        "login": EMAIL_OPERATION_EMAIL_LOGIN_VERIFICATION_CODE,
        "register": EMAIL_OPERATION_REGISTER_VERIFICATION_CODE,
        "reset_password": EMAIL_OPERATION_RESET_PASSWORD_VERIFICATION_CODE,
    }
    trigger_operation = operations.get(request.type, EMAIL_OPERATION_RESET_PASSWORD_VERIFICATION_CODE)
    client_ip = get_client_ip(http_request)
    owner_id = None
    pending_record = None
    cancellation = None
    needs_recovery = False
    rejection_detail = None

    async def reject(message: str, code: int = 40001, *, detail: str | None = None) -> ApiResponse:
        """提交本次拒绝的邮件日志后返回失败，日志不可用时明确提示用户。"""
        if needs_recovery:
            await rollback_session(db, operation="发送邮箱验证码")
        try:
            saved = await record_email_log(
                recipient_email=request.email, trigger_operation=trigger_operation,
                success=False, owner_id=owner_id, client_ip=client_ip, result_message=detail or message,
            )
        except Exception as exc:
            logger.opt(exception=exc).error(
                "验证码失败审计提交异常：email={} type={} client_ip={} reason={}",
                request.email, request.type, client_ip, detail or message,
            )
            saved = False
        return ApiResponse(
            success=False, code=code if saved else 50001,
            message=message if saved else f"{message}（邮件日志记录失败，请联系管理员）",
        )

    try:
        if request.type not in operations:
            raise CodeRequestRejected("验证码类型无效，请选择注册、登录或重置密码")
        existing_user = await UserService(db).get_by_email(request.email)
        owner_id = existing_user.id if existing_user else None
        # 被开关、后缀或其他条件拒绝的发信尝试也纳入频率限制。
        await check_email_code_limit(client_ip, request.email, request.type)
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
        # 邮件服务自身记录发送成功、SMTP 错误及配置缺失结果，入口不重复追加。
        success, message = await send_verification_code_email(
            request.email, code, request.type, owner_id=owner_id, client_ip=client_ip,
        )
        if not success:
            return ApiResponse(success=False, message=message)
        if email_code_store.get(request.email) is not pending_record:
            raise CodeRequestRejected("本次验证码已失效，请重新获取验证码")
        pending_record["expires_at"] = time.time() + 300
        pending_record["is_pending"] = False
        logger.info("发送邮箱验证码成功: email={} type={}", request.email, request.type)
        return ApiResponse(success=True, message="验证码已发送到您的邮箱，请查收")
    except (EmailDomainRejected, AuthRateLimitRejected, CodeRequestRejected) as exc:
        rejection_message, rejection_code = str(exc), exc.code
    except asyncio.CancelledError as exc:
        cancellation = exc
        needs_recovery = True
        rejection_message, rejection_code = "验证码发送请求已取消，本次验证码已失效", 50001
        logger.warning("发送邮箱验证码已取消: email={} type={}", request.email, request.type)
    except Exception as exc:
        logger.opt(exception=exc).error(
            "发送邮箱验证码失败: email={} type={} client_ip={}", request.email, request.type, client_ip,
        )
        needs_recovery = True
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
        try:
            await enforce_email_domain(setting_service.session, email)
        except EmailDomainRejected as exc:
            return ApiResponse(success=False, code=exc.code, message=str(exc))
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
