"""
邮箱验证码邮件发送服务。

功能：
1. 生成注册、登录及找回密码的验证码邮件内容
2. 返回配置缺失、SMTP 发送失败或真实投递成功的结果
3. 支持调用方统一审计，避免注册日志与邮件日志重复或分开提交
"""
from __future__ import annotations

from loguru import logger

from app.services.smtp_service import (
    get_encryption_by_port,
    get_smtp_settings,
    send_email_sync,
)
from common.services.email_log_service import (
    EMAIL_OPERATION_EMAIL_LOGIN_VERIFICATION_CODE,
    EMAIL_OPERATION_REGISTER_VERIFICATION_CODE,
    EMAIL_OPERATION_RESET_PASSWORD_VERIFICATION_CODE,
    record_email_log,
)


async def send_verification_code_email(
    to_email: str,
    code: str,
    code_type: str = "register",
    owner_id: int | None = None,
    client_ip: str | None = None,
    *,
    audit: bool = True,
) -> tuple[bool, str]:
    """
    发送验证码邮件

    Args:
        to_email: 收件邮箱
        code: 验证码
        code_type: 验证码类型 register / login / reset_password
        owner_id: 触发用户ID（找不到用户时为空）
        client_ip: 客户端IP
        audit: 是否由本服务记录邮件日志；False 时调用方须统一提交发送审计。
    Returns:
        (真实发送是否成功, 真实结果消息)，不会以模拟发送替代错误。
    """
    # 触发操作枚举：写入邮件发送日志时标识来源
    if code_type == "login":
        trigger_operation = EMAIL_OPERATION_EMAIL_LOGIN_VERIFICATION_CODE
    elif code_type == "register":
        trigger_operation = EMAIL_OPERATION_REGISTER_VERIFICATION_CODE
    else:
        trigger_operation = EMAIL_OPERATION_RESET_PASSWORD_VERIFICATION_CODE

    # 获取SMTP配置
    try:
        settings = await get_smtp_settings()
        smtp_server = settings.get('server', '')
        smtp_port = int(settings.get('port', 587))
        smtp_user = settings.get('user', '')
        smtp_password = settings.get('password', '')
        smtp_from = settings.get('from', '') or smtp_user
    except Exception as exc:  # noqa: BLE001 - 配置异常必须返回真实失败，调用方补齐联合审计
        logger.opt(exception=exc).error("读取验证码邮件配置失败")
        if audit:
            await record_email_log(
                recipient_email=to_email,
                trigger_operation=trigger_operation,
                success=False,
                owner_id=owner_id,
                client_ip=client_ip,
                result_message=f"读取邮件配置失败: {type(exc).__name__}: {exc}",
            )
        return False, "读取邮件配置失败，请稍后重试"
    
    # 根据端口自动判断加密方式
    use_tls, use_ssl = get_encryption_by_port(smtp_port)
    
    if not smtp_server or not smtp_user or not smtp_password:
        logger.warning("SMTP配置不完整，无法发送邮件")
        # 配置缺失同样必须落库邮件日志
        if audit:
            await record_email_log(
                recipient_email=to_email,
                trigger_operation=trigger_operation,
                success=False,
                owner_id=owner_id,
                client_ip=client_ip,
                result_message="邮件服务未配置，请联系管理员",
            )
        return False, "邮件服务未配置，请联系管理员"
    
    # 根据类型设置邮件内容
    if code_type == "register":
        subject = "注册验证码"
        action = "注册账号"
    elif code_type == "login":
        subject = "登录验证码"
        action = "登录账号"
    else:
        subject = "验证码"
        action = "操作"
    
    content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f4f7fa; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f4f7fa; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 480px; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);">
                    <!-- 头部 -->
                    <tr>
                        <td style="padding: 40px 40px 24px; text-align: center;">
                            <div style="width: 64px; height: 64px; margin: 0 auto 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 16px; display: flex; align-items: center; justify-content: center;">
                                <span style="font-size: 28px; color: #ffffff; line-height: 64px;">✉</span>
                            </div>
                            <h1 style="margin: 0; font-size: 24px; font-weight: 600; color: #1a1a2e;">验证码</h1>
                            <p style="margin: 8px 0 0; font-size: 14px; color: #6b7280;">您正在{action}</p>
                        </td>
                    </tr>
                    <!-- 验证码区域 -->
                    <tr>
                        <td style="padding: 0 40px;">
                            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 32px; text-align: center;">
                                <p style="margin: 0 0 8px; font-size: 12px; color: rgba(255,255,255,0.8); text-transform: uppercase; letter-spacing: 2px;">您的验证码</p>
                                <p style="margin: 0; font-size: 36px; font-weight: 700; color: #ffffff; letter-spacing: 8px; font-family: 'Courier New', monospace;">{code}</p>
                            </div>
                        </td>
                    </tr>
                    <!-- 提示信息 -->
                    <tr>
                        <td style="padding: 24px 40px 40px;">
                            <div style="background-color: #fef3c7; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                                <p style="margin: 0; font-size: 13px; color: #92400e; display: flex; align-items: center;">
                                    <span style="margin-right: 8px;">⏱</span>
                                    验证码有效期为 <strong style="margin: 0 4px;">5分钟</strong>，请尽快使用
                                </p>
                            </div>
                            <p style="margin: 0 0 12px; font-size: 13px; color: #6b7280; line-height: 1.6;">
                                • 请勿将验证码泄露给他人<br>
                                • 如非本人操作，请忽略此邮件
                            </p>
                        </td>
                    </tr>
                    <!-- 底部 -->
                    <tr>
                        <td style="padding: 20px 40px; background-color: #f9fafb; border-radius: 0 0 16px 16px; border-top: 1px solid #e5e7eb;">
                            <p style="margin: 0; font-size: 12px; color: #9ca3af; text-align: center;">
                                此邮件由系统自动发送，请勿直接回复
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    
    success, message = send_email_sync(
        to_email=to_email,
        subject=subject,
        content=content,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        smtp_from=smtp_from,
        use_tls=use_tls,
        use_ssl=use_ssl,
    )
    if audit:
        await record_email_log(
            recipient_email=to_email,
            trigger_operation=trigger_operation,
            success=success,
            owner_id=owner_id,
            client_ip=client_ip,
            result_message=message,
        )
    return success, message
