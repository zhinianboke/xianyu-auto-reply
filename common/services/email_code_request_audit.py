"""邮箱验证码拒绝审计：统一用途映射、用户识别及独立邮件失败日志提交。"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session_recovery import rollback_session
from common.models.registration_log import REGISTRATION_OPERATION_CODE
from common.schemas.common import ApiResponse
from common.services.email_log_service import (
    EMAIL_OPERATION_EMAIL_LOGIN_VERIFICATION_CODE,
    EMAIL_OPERATION_REGISTER_VERIFICATION_CODE,
    EMAIL_OPERATION_RESET_PASSWORD_VERIFICATION_CODE,
    EMAIL_OPERATION_VERIFICATION_CODE_REQUEST,
    record_email_log,
)
from common.services.registration_log_service import save_registration_audit
from common.services.user_auth_service import UserAuthService

EMAIL_CODE_OPERATIONS = {
    'login': EMAIL_OPERATION_EMAIL_LOGIN_VERIFICATION_CODE,
    'register': EMAIL_OPERATION_REGISTER_VERIFICATION_CODE,
    'reset_password': EMAIL_OPERATION_RESET_PASSWORD_VERIFICATION_CODE,
}


def email_code_operation(purpose: object) -> str:
    """返回可识别用途的字典值；无效用途使用参数拒绝项，不伪造找回密码操作。"""
    return EMAIL_CODE_OPERATIONS.get(purpose, EMAIL_OPERATION_VERIFICATION_CODE_REQUEST) if isinstance(purpose, str) else EMAIL_OPERATION_VERIFICATION_CODE_REQUEST


async def reject_email_code_request(
    session: AsyncSession, *, email: object, purpose: object, ip: str | None,
    message: str, code: int = 40001, owner_id: int | None = None,
    recover_session: bool = False, detail: str | None = None, preserve_code: bool = False,
    registration: bool | None = None,
) -> ApiResponse:
    """尽力识别触发用户并提交拒绝日志；查询故障不阻止独立审计或覆盖真实拒绝原因。

    Args:
        session: 请求会话，仅用于识别触发用户，不修改业务数据。
        email/purpose/ip: 请求中的收件邮箱、用途和公共方法取得的客户端 IP。
        message/code: 用户应看到的真实业务拒绝原因和错误码。
        owner_id: 已识别用户编号；为空时在受保护的收尾中查找。
        recover_session: 查询前恢复发生异常的会话。
        detail: 审计原因；省略时使用 message。
        preserve_code: IP 封禁时保持原统一业务码，另附审计故障提示。
        registration: 是否明确注册用途；旧默认用途请求由入口传 False，避免误记注册。
    Returns:
        日志已经尝试提交的统一失败响应；调用方负责取消保护。
    """
    # 原始注册字段以长文本完整审计；仅合法长度的字符串用于真实用户定位。
    recipient = email if isinstance(email, str) else ''
    registration = purpose == 'register' if registration is None else registration
    session_ready = not recover_session or await rollback_session(session, operation='验证码拒绝用户识别')
    if session_ready and owner_id is None and recipient and len(recipient) <= 255:
        try:
            user = await UserAuthService(session).find_login_user(recipient, by_email=True)
            owner_id = user.id if user is not None else None
        except Exception as exc:  # noqa: BLE001 - 用户查询失败仍必须写独立审计
            logger.opt(exception=exc).error(
                '验证码拒绝用户识别失败：email={} purpose={} client_ip={} reason={}',
                email, purpose, ip, message,
            )
            await rollback_session(session, operation='验证码拒绝用户识别')
    try:
        if registration:
            await rollback_session(session, operation='注册验证码拒绝审计')
            await save_registration_audit(
                email=email, operation=REGISTRATION_OPERATION_CODE, success=False,
                ip=ip, message=detail or message, owner_id=owner_id,
                email_operation=email_code_operation(purpose),
            )
            saved = True
        else:
            saved = await record_email_log(
                recipient_email=recipient, trigger_operation=email_code_operation(purpose),
                success=False, owner_id=owner_id, client_ip=ip, result_message=detail or message,
            )
    except Exception as exc:  # noqa: BLE001 - 独立审计故障明确展示给用户
        logger.opt(exception=exc).error(
            '验证码拒绝审计失败：email={} purpose={} client_ip={} reason={}', email, purpose, ip, detail or message,
        )
        saved = False
    return ApiResponse(
        success=False, code=code if saved or preserve_code else 50001,
        message=message if saved else f'{message}（{"注册及邮件日志记录失败" if registration else "邮件日志记录失败"}，请联系管理员）', data=None,
    )
