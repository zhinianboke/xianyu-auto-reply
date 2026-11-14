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
from common.services.registration_policy import get_registration_rejection_message
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


@router.post("/send-email-code")
async def send_email_verification_code(
    http_request: Request,
    request: SendCodeRequest,
    db: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """按用途和当前注册策略发送验证码，并记录邮件结果。

    Args:
        http_request: 请求对象，供公共方法读取客户端 IP。
        request: 收件邮箱、邮件用途及滑动验证信息。
        db: 当前请求的数据库会话。
    Returns:
        统一业务响应；关闭注册时不生成验证码、不发送邮件。
    """
    # 触发操作枚举与客户端IP，用于邮件发送日志
    if request.type == "login":
        trigger_operation = EMAIL_OPERATION_EMAIL_LOGIN_VERIFICATION_CODE
    elif request.type == "register":
        trigger_operation = EMAIL_OPERATION_REGISTER_VERIFICATION_CODE
    else:
        trigger_operation = EMAIL_OPERATION_RESET_PASSWORD_VERIFICATION_CODE
    client_ip = get_client_ip(http_request)

    existing_user = None
    pending_record = None
    try:
        if request.type not in {"register", "login", "reset_password"}:
            message = "验证码类型无效，请选择注册、登录或重置密码"
            await record_email_log(
                recipient_email=request.email,
                trigger_operation=trigger_operation,
                success=False,
                owner_id=None,
                client_ip=client_ip,
                result_message=f"{message}（收到的类型：{request.type}）",
            )
            return ApiResponse(success=False, message=message)

        user_service = UserService(db)
        if request.type == "register":
            settings = await SystemSettingService(db).list_settings()
            rejection_message = get_registration_rejection_message(settings)
            if rejection_message:
                existing_user = await user_service.get_by_email(request.email)
                log_saved = await record_email_log(
                    recipient_email=request.email,
                    trigger_operation=trigger_operation,
                    success=False,
                    owner_id=(existing_user.id if existing_user else None),
                    client_ip=client_ip,
                    result_message=rejection_message,
                )
                return ApiResponse(
                    success=False,
                    code=status.HTTP_403_FORBIDDEN,
                    message=(
                        rejection_message if log_saved else f"{rejection_message}（邮件日志记录失败，请联系管理员）"
                    ),
                )

        cleanup_expired_email_codes()
        # 忘记密码场景：参照登录逻辑，开启滑动验证时必须先通过极验二次验证
        if request.type == "reset_password":
            setting_service = SystemSettingService(db)
            all_settings = await setting_service.list_settings()
            captcha_enabled_str = all_settings.get("login_captcha_enabled")
            captcha_enabled = captcha_enabled_str in (None, "true", "1")  # 默认开启
            if captcha_enabled:
                if not request.geetest_challenge:
                    # 被校验拒绝也必须落库邮件日志
                    await record_email_log(
                        recipient_email=request.email,
                        trigger_operation=trigger_operation,
                        success=False,
                        owner_id=None,
                        client_ip=client_ip,
                        result_message="请完成滑动验证",
                    )
                    return ApiResponse(success=False, message="请完成滑动验证")

                geetest_ok, geetest_msg = check_geetest_verified(request.geetest_challenge)
                if not geetest_ok:
                    # 被校验拒绝也必须落库邮件日志
                    await record_email_log(
                        recipient_email=request.email,
                        trigger_operation=trigger_operation,
                        success=False,
                        owner_id=None,
                        client_ip=client_ip,
                        result_message=geetest_msg,
                    )
                    return ApiResponse(success=False, message=geetest_msg)

        # 根据类型检查邮箱
        if request.type == "register":
            existing_user = await user_service.get_by_email(request.email)
            if existing_user:
                await record_email_log(
                    recipient_email=request.email,
                    trigger_operation=trigger_operation,
                    success=False,
                    owner_id=existing_user.id,
                    client_ip=client_ip,
                    result_message="该邮箱已被注册",
                )
                return ApiResponse(
                    success=False,
                    message="该邮箱已被注册"
                )
        elif request.type == "login":
            existing_user = await user_service.get_by_email(request.email)
            if not existing_user:
                await record_email_log(
                    recipient_email=request.email,
                    trigger_operation=trigger_operation,
                    success=False,
                    owner_id=None,
                    client_ip=client_ip,
                    result_message="该邮箱未注册",
                )
                return ApiResponse(
                    success=False,
                    message="该邮箱未注册"
                )
        elif request.type == "reset_password":
            existing_user = await user_service.get_by_email(request.email)
            if not existing_user:
                await record_email_log(
                    recipient_email=request.email,
                    trigger_operation=trigger_operation,
                    success=False,
                    owner_id=None,
                    client_ip=client_ip,
                    result_message="该邮箱未注册",
                )
                return ApiResponse(
                    success=False,
                    message="该邮箱未注册"
                )

        # 检查发送频率（1分钟内只能发送一次）
        stored = email_code_store.get(request.email)
        if stored and (stored.get("is_pending") or stored["expires_at"] - 240 > time.time()):
            await record_email_log(
                recipient_email=request.email,
                trigger_operation=trigger_operation,
                success=False,
                owner_id=(existing_user.id if existing_user else None),
                client_ip=client_ip,
                result_message="验证码发送过于频繁，请稍后再试",
            )
            return ApiResponse(
                success=False,
                message="验证码发送过于频繁，请稍后再试"
            )

        # 生成验证码
        code = generate_verification_code()

        # 发送期间占用本次记录但不允许消费，成功后再开放校验。
        pending_record = {
            "code": code,
            "type": request.type,
            "expires_at": time.time() + 300,
            "is_pending": True,
        }
        email_code_store[request.email] = pending_record

        # 发送邮件
        success, message = await send_verification_code_email(
            request.email,
            code,
            request.type,
            owner_id=(existing_user.id if existing_user else None),
            client_ip=client_ip,
        )

        if not success:
            return ApiResponse(
                success=False,
                message=message
            )

        if email_code_store.get(request.email) is not pending_record:
            return ApiResponse(success=False, message="本次验证码已失效，请重新获取验证码")
        pending_record["expires_at"] = time.time() + 300
        pending_record["is_pending"] = False
        logger.info(f"发送邮箱验证码成功: email={request.email}, type={request.type}")

        return ApiResponse(
            success=True,
            message="验证码已发送到您的邮箱，请查收"
        )

    except asyncio.CancelledError:
        logger.warning(
            "发送邮箱验证码已取消: email={} type={} client_ip={}",
            request.email, request.type, client_ip,
        )
        await record_email_log(
            recipient_email=request.email,
            trigger_operation=trigger_operation,
            success=False,
            owner_id=(existing_user.id if existing_user else None),
            client_ip=client_ip,
            result_message="验证码发送请求已取消，本次验证码已失效",
        )
        raise
    except Exception as e:
        logger.opt(exception=e).error(
            "发送邮箱验证码失败: email={} type={} client_ip={} exception_type={} exception={}",
            request.email, request.type, client_ip, type(e).__name__, e,
        )
        # 兜底记录：异常也必须落库邮件日志，禁止静默失败
        await record_email_log(
            recipient_email=str(getattr(request, "email", "") or ""),
            trigger_operation=trigger_operation,
            success=False,
            owner_id=(existing_user.id if existing_user else None),
            client_ip=client_ip,
            result_message=f"发送邮箱验证码异常: {type(e).__name__}: {e}",
        )
        return ApiResponse(
            success=False,
            message="验证码发送失败，请稍后重试"
        )
    finally:
        if pending_record is not None and pending_record.get("is_pending"):
            invalidate_email_code(request.email, pending_record)


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
