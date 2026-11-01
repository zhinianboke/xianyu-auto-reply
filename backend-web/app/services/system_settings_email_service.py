"""系统设置测试邮件参数校验与审计服务。"""
from __future__ import annotations

from common.services.email_log_service import (
    EMAIL_OPERATION_TEST_EMAIL,
    record_email_log,
)
from common.utils.email_utils import normalize_email_address


async def validate_test_email_recipient(
    email: str,
    *,
    owner_id: int,
    client_ip: str | None,
) -> tuple[str | None, str | None]:
    """
    校验测试邮件收件地址，并记录被拒绝的发送尝试。

    Args:
        email: 用户输入的收件地址。
        owner_id: 触发操作的用户ID。
        client_ip: 客户端IP。
    Returns:
        (规范化邮箱, 错误信息)。
    """
    normalized_email, error_message = normalize_email_address(email)
    if error_message:
        await record_email_log(
            recipient_email=str(email or "").strip(),
            trigger_operation=EMAIL_OPERATION_TEST_EMAIL,
            success=False,
            owner_id=owner_id,
            client_ip=client_ip,
            result_message=error_message,
        )
    return normalized_email, error_message
