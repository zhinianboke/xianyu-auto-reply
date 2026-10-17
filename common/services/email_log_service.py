"""
邮件发送日志写入服务

功能：
1. 汇总所有邮件发送入口的触发操作枚举值
2. 统一向 xy_email_logs 追加发送成功、失败、限流或配置缺失记录
3. 写日志失败时记录错误，不影响邮件发送主流程
"""
from __future__ import annotations

import asyncio

from loguru import logger

from common.db.session import async_session_maker
from common.models.email_log import XYEmailLog

# 邮件触发操作枚举（与数据字典 xy_data_dictionaries / email_trigger_operation 保持一致）
EMAIL_OPERATION_REGISTER_VERIFICATION_CODE = "register_verification_code"
EMAIL_OPERATION_RESET_PASSWORD_VERIFICATION_CODE = "reset_password_verification_code"
EMAIL_OPERATION_EMAIL_LOGIN_VERIFICATION_CODE = "email_login_verification_code"
EMAIL_OPERATION_TEST_EMAIL = "test_email"
EMAIL_OPERATION_WITHDRAW_NOTIFICATION = "withdraw_notification"
EMAIL_OPERATION_NOTIFICATION_CHANNEL_TEST = "notification_channel_test"

EMAIL_SEND_RESULT_SUCCESS = "success"
EMAIL_SEND_RESULT_FAILURE = "failure"


async def record_email_log(
    *,
    recipient_email: str,
    trigger_operation: str,
    success: bool,
    owner_id: int | None = None,
    client_ip: str | None = None,
    result_message: str | None = None,
) -> bool:
    """追加一条邮件发送日志。

    Args:
        recipient_email: 收件邮箱。
        trigger_operation: 触发操作枚举值。
        success: 是否发送成功。
        owner_id: 触发用户 ID；找不到用户时为空。
        client_ip: 客户端 IP。
        result_message: 成功结果或失败原因。
    Returns:
        是否成功写入；写入失败重试后返回 False，不影响邮件发送主流程。
    """
    for attempt in range(1, 4):
        try:
            log = XYEmailLog(
                owner_id=owner_id,
                recipient_email=str(recipient_email or ""),
                trigger_operation=str(trigger_operation or ""),
                success=bool(success),
                client_ip=(str(client_ip).strip() if client_ip else None),
                result_message=(str(result_message) if result_message is not None else None),
            )
            async with async_session_maker() as session:
                session.add(log)
                await session.commit()
            return True
        except Exception as exc:
            if attempt < 3:
                logger.warning(
                    "写入邮件发送日志失败，将重试: "
                    f"attempt={attempt}, recipient_email={recipient_email}, "
                    f"trigger_operation={trigger_operation}, error={type(exc).__name__}: {exc}"
                )
                await asyncio.sleep(attempt * 0.2)
                continue
            logger.error(
                "写入邮件发送日志最终失败: "
                f"recipient_email={recipient_email}, trigger_operation={trigger_operation}, "
                f"success={success}, owner_id={owner_id}, client_ip={client_ip}, "
                f"result_message={result_message}, error={type(exc).__name__}: {exc}"
            )
    return False


__all__ = [
    "EMAIL_OPERATION_REGISTER_VERIFICATION_CODE",
    "EMAIL_OPERATION_RESET_PASSWORD_VERIFICATION_CODE",
    "EMAIL_OPERATION_EMAIL_LOGIN_VERIFICATION_CODE",
    "EMAIL_OPERATION_TEST_EMAIL",
    "EMAIL_OPERATION_WITHDRAW_NOTIFICATION",
    "EMAIL_OPERATION_NOTIFICATION_CHANNEL_TEST",
    "EMAIL_SEND_RESULT_SUCCESS",
    "EMAIL_SEND_RESULT_FAILURE",
    "record_email_log",
]
