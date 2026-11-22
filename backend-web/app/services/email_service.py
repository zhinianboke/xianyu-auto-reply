"""
邮件业务入口及旧公共接口兼容导出。

功能：
1. 发送测试邮件与提现通知邮件
2. 兼容既有 SMTP 公共方法和验证码邮件发送导入路径
3. SMTP 与验证码邮件实现分别由独立公共模块维护
"""
from __future__ import annotations

from loguru import logger

from app.core.config import get_settings
from app.services.settlement_service import (
    generate_review_token,
    get_withdraw_notify_email,
)
from app.services.smtp_service import (
    _diagnose_smtp_config,
    get_encryption_by_port,
    get_smtp_settings,
    send_email_sync,
)
from app.services.verification_email_service import send_verification_code_email
from app.services.withdraw_risk_check import run_all_checks
from common.services.email_log_service import (
    EMAIL_OPERATION_TEST_EMAIL,
    EMAIL_OPERATION_WITHDRAW_NOTIFICATION,
    record_email_log,
)
from common.utils.time_utils import get_beijing_now_naive

__all__ = [
    "_diagnose_smtp_config",
    "get_encryption_by_port",
    "get_smtp_settings",
    "send_email_sync",
    "send_test_email",
    "send_verification_code_email",
    "send_withdraw_notification_email",
]


async def send_test_email(
    to_email: str,
    owner_id: int | None = None,
    client_ip: str | None = None,
) -> tuple[bool, str]:
    """
    发送测试邮件

    Args:
        to_email: 收件邮箱
        owner_id: 触发用户ID
        client_ip: 客户端IP
    Returns:
        (是否成功, 消息)
    """
    try:
        settings = await get_smtp_settings()
        smtp_server = settings.get('server', '')
        smtp_port = int(settings.get('port', 587))
        smtp_user = settings.get('user', '')
        smtp_password = settings.get('password', '')
        smtp_from = settings.get('from', '') or smtp_user
    except Exception as exc:  # noqa: BLE001 - 保留测试邮件原有配置异常审计及中文反馈
        logger.opt(exception=exc).error("读取测试邮件配置失败")
        await record_email_log(
            recipient_email=to_email,
            trigger_operation=EMAIL_OPERATION_TEST_EMAIL,
            success=False,
            owner_id=owner_id,
            client_ip=client_ip,
            result_message=f"读取邮件配置失败: {type(exc).__name__}: {exc}",
        )
        return False, "读取邮件配置失败，请稍后重试"
    
    # 根据端口自动判断加密方式
    use_tls, use_ssl = get_encryption_by_port(smtp_port)
    
    if not smtp_server or not smtp_user or not smtp_password:
        # 配置缺失同样必须落库邮件日志
        await record_email_log(
            recipient_email=to_email,
            trigger_operation=EMAIL_OPERATION_TEST_EMAIL,
            success=False,
            owner_id=owner_id,
            client_ip=client_ip,
            result_message="SMTP配置不完整，请先填写SMTP服务器、用户名和密码",
        )
        return False, "SMTP配置不完整，请先填写SMTP服务器、用户名和密码"
    
    content = """
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
                            <div style="width: 64px; height: 64px; margin: 0 auto 20px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border-radius: 16px;">
                                <span style="font-size: 28px; color: #ffffff; line-height: 64px;">✓</span>
                            </div>
                            <h1 style="margin: 0; font-size: 24px; font-weight: 600; color: #1a1a2e;">配置测试成功</h1>
                        </td>
                    </tr>
                    <!-- 内容区域 -->
                    <tr>
                        <td style="padding: 0 40px 32px;">
                            <div style="background-color: #ecfdf5; border-radius: 12px; padding: 24px; text-align: center;">
                                <p style="margin: 0; font-size: 15px; color: #065f46; line-height: 1.6;">
                                    恭喜！您的 SMTP 邮件配置正确。<br>
                                    系统已可以正常发送邮件通知。
                                </p>
                            </div>
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
        subject="邮件配置测试",
        content=content,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        smtp_from=smtp_from,
        use_tls=use_tls,
        use_ssl=use_ssl,
    )
    await record_email_log(
        recipient_email=to_email,
        trigger_operation=EMAIL_OPERATION_TEST_EMAIL,
        success=success,
        owner_id=owner_id,
        client_ip=client_ip,
        result_message=message,
    )
    return success, message


def _build_risk_html(risk_result) -> str:
    """将风控检验结果渲染为邮件内嵌 HTML 块"""
    has_issue = risk_result.has_issue
    header_bg = '#fef2f2' if has_issue else '#f0fdf4'
    header_border = '#fecaca' if has_issue else '#bbf7d0'
    header_color = '#dc2626' if has_issue else '#16a34a'
    header_icon = '⚠️' if has_issue else '✅'
    header_text = '余额真实性检验：发现异常，请仔细核查后再打款' if has_issue else '余额真实性检验：全部通过'

    rows = ''
    for item in risk_result.items:
        icon = '❌' if not item.passed else '✅'
        row_bg = '#fff7ed' if not item.passed else '#ffffff'
        border_left = '4px solid #f97316' if not item.passed else '4px solid #d1fae5'
        rows += f'''
<tr>
  <td style="padding:10px 12px;background:{row_bg};border-left:{border_left};border-bottom:1px solid #f1f5f9;">
    <div style="font-size:13px;font-weight:600;color:#1f2937;">{icon} {item.title}</div>
    <div style="font-size:12px;color:#4b5563;margin-top:4px;">{item.summary}</div>'''
        if item.issues:
            rows += '<ul style="margin:6px 0 0 16px;padding:0;font-size:12px;color:#dc2626;">'
            for issue in item.issues:
                rows += f'<li style="margin-bottom:2px;">{issue}</li>'
            rows += '</ul>'
        rows += '</td></tr>'

    return f'''
<tr>
  <td style="padding: 24px 40px 0;">
    <div style="border:1px solid {header_border};border-radius:10px;overflow:hidden;">
      <div style="background:{header_bg};padding:12px 16px;border-bottom:1px solid {header_border};">
        <span style="font-size:14px;font-weight:700;color:{header_color};">{header_icon} {header_text}</span>
      </div>
      <table width="100%" cellspacing="0" cellpadding="0">{rows}</table>
    </div>
  </td>
</tr>'''


async def send_withdraw_notification_email(
    user_id: int,
    username: str,
    amount: str,
    alipay_id: str,
    record_id: int,
    balance_after: str,
    payment_type: str = 'alipay',
    payment_qrcode: str = '',
) -> tuple[bool, str]:
    """
    发送提现通知邮件到管理员
    
    Args:
        user_id: 用户ID
        username: 用户名
        amount: 提现金额
        alipay_id: 支付宝ID
        record_id: 结算记录ID
        balance_after: 提现后余额
    
    Returns:
        (是否成功, 消息)
    """
    # 从系统设置获取提现通知邮箱
    to_email = await get_withdraw_notify_email()
    if not to_email:
        logger.warning("系统未配置提现通知邮箱，无法发送提现通知")
        # 收件邮箱未知，仍必须落库邮件日志
        await record_email_log(
            recipient_email="",
            trigger_operation=EMAIL_OPERATION_WITHDRAW_NOTIFICATION,
            success=False,
            owner_id=user_id,
            result_message="系统未配置提现通知邮箱",
        )
        return False, "系统未配置提现通知邮箱"
    
    # 获取SMTP配置
    settings = await get_smtp_settings()
    
    smtp_server = settings.get('server', '')
    smtp_port = int(settings.get('port', 587))
    smtp_user = settings.get('user', '')
    smtp_password = settings.get('password', '')
    smtp_from = settings.get('from', '') or smtp_user
    
    use_tls, use_ssl = get_encryption_by_port(smtp_port)
    
    if not smtp_server or not smtp_user or not smtp_password:
        logger.warning("SMTP配置不完整，无法发送提现通知邮件")
        await record_email_log(
            recipient_email=to_email,
            trigger_operation=EMAIL_OPERATION_WITHDRAW_NOTIFICATION,
            success=False,
            owner_id=user_id,
            result_message="邮件服务未配置",
        )
        return False, "邮件服务未配置"
    
    
    # 生成审核链接
    # 公网访问地址从配置读取，避免写死域名，方便他人部署
    base_url = get_settings().backend_web_public_url.rstrip('/')
    approve_token = generate_review_token(record_id, "approve")
    reject_token = generate_review_token(record_id, "reject")
    approve_url = f"{base_url}/api/v1/payment/withdraw/review?id={record_id}&action=approve&token={approve_token}"
    reject_url = f"{base_url}/api/v1/payment/withdraw/review?id={record_id}&action=reject&token={reject_token}"
    
    # 当前时间
    now_str = get_beijing_now_naive().strftime("%Y-%m-%d %H:%M:%S")

    # ── 风控检验 ──────────────────────────────────────────────────────────
    risk_html = ''
    try:
        risk_result = await run_all_checks(user_id, balance_after, record_id)
        risk_html = _build_risk_html(risk_result)
    except Exception as e:  # noqa: BLE001 - 保留提现邮件的风控故障提示，不影响既有发信流程
        logger.warning(f"风控检验执行失败: {e}")
        risk_html = '<p style="color:#ef4444;font-size:13px">⚠️ 风控检验执行异常，请手动核查</p>'
    # ─────────────────────────────────────────────────────────────────────

    # 收款码展示：使用 URL 引用，避免 Base64 数据触发反垃圾邮件过滤
    payment_type_label = '微信' if payment_type == 'wechat' else '支付宝'
    qrcode_img_html = ''
    if payment_qrcode:
        # 构造可公开访问的图片 URL
        img_url = payment_qrcode if payment_qrcode.startswith('http') else f"{base_url}{payment_qrcode}"
        qrcode_img_html = f'''<div style="margin:0 0 10px;text-align:center;">
  <img src="{img_url}" alt="{payment_type_label}收款码"
       width="180" height="180"
       style="border:1px solid #e5e7eb;border-radius:8px;object-fit:contain;" />
  <p style="margin:4px 0 0;font-size:11px;color:#9ca3af;">若图片未显示，请访问：{img_url}</p>
</div>'''

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
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 520px; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);">
                    <!-- 头部 -->
                    <tr>
                        <td style="padding: 40px 40px 24px; text-align: center;">
                            <div style="width: 64px; height: 64px; margin: 0 auto 20px; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); border-radius: 16px;">
                                <span style="font-size: 28px; color: #ffffff; line-height: 64px;">💰</span>
                            </div>
                            <h1 style="margin: 0; font-size: 24px; font-weight: 600; color: #1a1a2e;">提现申请通知</h1>
                            <p style="margin: 8px 0 0; font-size: 14px; color: #6b7280;">收到新的提现申请，请及时处理</p>
                        </td>
                    </tr>
                    <!-- 提现详情 -->
                    <tr>
                        <td style="padding: 0 40px;">
                            <div style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border-radius: 12px; padding: 24px;">
                                <table width="100%" cellspacing="0" cellpadding="8" style="font-size: 14px; color: #1f2937;">
                                    <tr>
                                        <td style="font-weight: 600; width: 100px;">记录ID：</td>
                                        <td>{record_id}</td>
                                    </tr>
                                    <tr>
                                        <td style="font-weight: 600;">用户ID：</td>
                                        <td>{user_id}</td>
                                    </tr>
                                    <tr>
                                        <td style="font-weight: 600;">用户名：</td>
                                        <td>{username}</td>
                                    </tr>
                                    <tr>
                                        <td style="font-weight: 600;">提现金额：</td>
                                        <td style="color: #dc2626; font-weight: 700; font-size: 18px;">¥{amount}</td>
                                    </tr>
                                    <tr>
                                        <td style="font-weight: 600;">支付宝ID：</td>
                                        <td style="font-family: monospace;">{alipay_id}</td>
                                    </tr>
                                    <tr>
                                        <td style="font-weight: 600;">提现后余额：</td>
                                        <td>¥{balance_after}</td>
                                    </tr>
                                    <tr>
                                        <td style="font-weight: 600;">申请时间：</td>
                                        <td>{now_str}</td>
                                    </tr>
                                </table>
                            </div>
                        </td>
                    </tr>
                    <!-- 审核按钮区域 -->
                    <tr>
                        <td style="padding: 24px 40px 0;">
                            <div style="text-align: center;">
                                <p style="margin: 0 0 16px; font-size: 15px; color: #374151; font-weight: 600;">审核操作</p>
                                <div style="display: inline-block;">
                                    <a href="{approve_url}" style="display: inline-block; padding: 12px 32px; margin: 0 8px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: #ffffff; text-decoration: none; border-radius: 8px; font-size: 15px; font-weight: 600;">✓ 审核通过</a>
                                    <a href="{reject_url}" style="display: inline-block; padding: 12px 32px; margin: 0 8px; background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); color: #ffffff; text-decoration: none; border-radius: 8px; font-size: 15px; font-weight: 600;">✗ 审核拒绝</a>
                                </div>
                                <p style="margin: 12px 0 0; font-size: 12px; color: #9ca3af;">点击按钮将直接更新结算记录状态</p>
                            </div>
                        </td>
                    </tr>
                    <!-- 风控检验结果 -->
                    {risk_html}
                    <!-- 转账操作提示 -->
                    <tr>
                        <td style="padding: 24px 40px 0;">
                            <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 10px; padding: 18px 20px;">
                                <p style="margin: 0 0 12px; font-size: 14px; font-weight: 600; color: #1e40af;">转账操作（{payment_type_label}收款码）</p>
                                {qrcode_img_html}
                                <table width="100%" cellspacing="0" cellpadding="6" style="font-size: 14px;">
                                    <tr>
                                        <td style="color: #6b7280; width: 80px;">转账金额：</td>
                                        <td style="font-size: 16px; font-weight: 700; color: #dc2626;">¥{amount}</td>
                                    </tr>
                                    <tr>
                                        <td style="color: #6b7280;">转账备注：</td>
                                        <td style="color: #374151;">提现{record_id}</td>
                                    </tr>
                                </table>
                            </div>
                        </td>
                    </tr>
                    <!-- 底部 -->
                    <tr>
                        <td style="padding: 32px 40px 20px;">
                            <div style="padding-top: 20px; border-top: 1px solid #e5e7eb;">
                                <p style="margin: 0; font-size: 12px; color: #9ca3af; text-align: center;">
                                    此邮件由系统自动发送，请勿直接回复
                                </p>
                            </div>
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
        subject=f"【提现通知】用户 {username} 申请提现 ¥{amount}",
        content=content,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        smtp_from=smtp_from,
        use_tls=use_tls,
        use_ssl=use_ssl,
    )
    await record_email_log(
        recipient_email=to_email,
        trigger_operation=EMAIL_OPERATION_WITHDRAW_NOTIFICATION,
        success=success,
        owner_id=user_id,
        client_ip=None,
        result_message=message,
    )
    return success, message
