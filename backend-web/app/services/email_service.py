"""
邮件服务

功能：
1. 发送邮件（支持SMTP）
2. 发送验证码邮件
3. 发送测试邮件
"""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from common.db.session import async_session_maker
from common.utils.time_utils import get_beijing_now_naive


async def get_smtp_settings() -> dict:
    """从数据库获取SMTP配置"""
    from sqlalchemy import text
    
    async with async_session_maker() as session:
        result = await session.execute(
            text("SELECT `key`, value FROM xy_system_settings WHERE `key` LIKE 'smtp_%'")
        )
        rows = result.fetchall()
        
        settings = {}
        for row in rows:
            key = row[0].replace('smtp_', '')
            settings[key] = row[1]
        
        return settings


def get_encryption_by_port(port: int) -> tuple[bool, bool]:
    """
    根据端口自动判断加密方式
    返回: (use_tls, use_ssl)

    规则：
      - 465: SSL（隐式 TLS）— 大多数国内邮箱推荐
      - 587: STARTTLS（显式 TLS）— Gmail/Outlook 推荐；163/QQ 不支持
      - 25:  无加密 — Docker 容器会被运营商封禁出站
      - 994: SSL（部分服务商支持）
    """
    if port in (465, 994):
        return False, True  # SSL
    elif port == 587:
        return True, False  # TLS (STARTTLS)
    else:
        return False, False  # 无加密 (端口25等)


def _diagnose_smtp_config(smtp_server: str, smtp_port: int) -> Optional[str]:
    """
    根据服务器域名和端口给出常见错误诊断
    返回错误提示字符串；None 表示配置看起来正常
    """
    server_lower = (smtp_server or '').lower()
    # 163/126/yeah 网易邮箱
    if any(x in server_lower for x in ('163.com', '126.com', 'yeah.net')):
        if smtp_port == 587:
            return (
                "网易邮箱（163/126/yeah）不支持端口 587/STARTTLS，"
                "请改为端口 465（SSL）"
            )
        if smtp_port == 25:
            return (
                "网易邮箱端口 25 通常被云服务商/运营商封禁出站连接，"
                "建议改为端口 465（SSL）"
            )
    # QQ 邮箱
    if 'qq.com' in server_lower:
        if smtp_port == 587:
            return (
                "QQ 邮箱不支持端口 587/STARTTLS，"
                "请改为端口 465（SSL）"
            )
    return None


def send_email_sync(
    to_email: str,
    subject: str,
    content: str,
    smtp_server: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    smtp_from: Optional[str] = None,
    use_tls: bool = True,
    use_ssl: bool = False,
) -> tuple[bool, str]:
    """
    同步发送邮件
    返回: (是否成功, 消息)
    """
    server = None
    # 当前执行到哪一步（用于错误诊断）
    stage = "初始化"
    try:
        from email.utils import formataddr, formatdate
        import email.charset

        # 设置编码
        email.charset.add_charset('utf-8', email.charset.SHORTEST, email.charset.BASE64, 'utf-8')

        # 创建邮件
        msg = MIMEMultipart('alternative')

        # 发件人格式化（防止被判为垃圾邮件）
        from_name = smtp_from or "系统通知"
        msg['From'] = formataddr((from_name, smtp_user))
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = f"<{smtp_user.replace('@', '.')}.{int(__import__('time').time())}@mail>"

        # 添加纯文本版本（提高送达率）
        text_content = content.replace('<br>', '\n').replace('</p>', '\n')
        import re
        text_content = re.sub(r'<[^>]+>', '', text_content)
        msg.attach(MIMEText(text_content, 'plain', 'utf-8'))

        # 添加HTML内容
        msg.attach(MIMEText(content, 'html', 'utf-8'))

        # 打印邮件信息到日志（含连接参数，便于排错；不打印正文与密码）
        logger.info(
            f"准备发送邮件: to={to_email}, subject={subject}, "
            f"server={smtp_server}, port={smtp_port}, "
            f"use_ssl={use_ssl}, use_tls={use_tls}, user={smtp_user}"
        )

        # 配置预诊断（端口/加密不匹配等）
        config_warning = _diagnose_smtp_config(smtp_server, smtp_port)
        if config_warning:
            logger.warning(f"SMTP 配置预诊断: {config_warning}")

        # 连接SMTP服务器
        stage = f"连接服务器 {smtp_server}:{smtp_port}"
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
            stage = "EHLO 握手"
            server.ehlo()
            if use_tls:
                stage = "STARTTLS 协商"
                server.starttls()
                server.ehlo()

        # 登录
        stage = "SMTP 认证（登录）"
        server.login(smtp_user, smtp_password)

        # 发送邮件
        stage = "投递邮件"
        server.sendmail(smtp_user, [to_email], msg.as_string())

        try:
            server.quit()
        except Exception:
            # quit 失败不影响发送结果
            pass

        logger.info(f"邮件发送成功: to={to_email}, subject={subject}")
        return True, "邮件发送成功"

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP认证失败 (stage={stage}): code={e.smtp_code}, msg={e.smtp_error!r}")
        # 网易/QQ 邮箱：登录密码 ≠ 授权码，常见原因
        hint = ""
        sl = (smtp_server or '').lower()
        if any(x in sl for x in ('163.com', '126.com', 'yeah.net', 'qq.com')):
            hint = "（请确认使用的是邮箱「客户端授权码」，不是登录密码；并已在邮箱后台开启 SMTP 服务）"
        return False, f"SMTP 认证失败，请检查用户名和密码{hint}"
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP连接失败 (stage={stage}): {e}")
        return False, f"SMTP 服务器连接失败，请检查服务器地址和端口（{smtp_server}:{smtp_port}）"
    except smtplib.SMTPServerDisconnected as e:
        # 这就是用户报错的"Connection unexpectedly closed"
        logger.error(f"SMTP连接被服务器关闭 (stage={stage}): {e}")
        config_warning = _diagnose_smtp_config(smtp_server, smtp_port)
        hint = f"（{config_warning}）" if config_warning else (
            "（常见原因：1) 端口/加密方式不匹配；2) 邮箱后台未开启 SMTP 服务；"
            "3) 授权码错误次数过多被限制；4) 容器环境出站端口被封）"
        )
        return False, f"SMTP 服务器在「{stage}」阶段意外关闭连接{hint}"
    except smtplib.SMTPException as e:
        logger.error(f"SMTP错误 (stage={stage}): {type(e).__name__}: {e}")
        return False, f"邮件发送失败（{stage}）: {type(e).__name__}: {str(e)}"
    except (OSError, TimeoutError) as e:
        logger.error(f"SMTP网络异常 (stage={stage}): {type(e).__name__}: {e}")
        return False, f"SMTP 网络异常（{stage}）: {type(e).__name__}: {str(e)}"
    except Exception as e:
        # 注意：避免用 f-string 把 str(e) 拼进 message 后再传给 loguru，
        # 因为 loguru 会对 message 调 str.format()，str(e) 中的 '{xxx}' 会被误认作占位符。
        # 使用 logger.opt(exception=e) 自动附带 traceback，参数走位置占位符 {} 安全。
        logger.opt(exception=e).error(
            "发送邮件失败 (stage={}): {}: {}",
            stage, type(e).__name__, str(e),
        )
        return False, f"发送邮件失败（{stage}）: {type(e).__name__}: {str(e)}"
    finally:
        # 异常路径也确保连接关闭，避免文件句柄/socket 泄漏
        if server is not None:
            try:
                server.close()
            except Exception:
                pass


async def send_verification_code_email(to_email: str, code: str, code_type: str = "register") -> tuple[bool, str]:
    """
    发送验证码邮件
    返回: (是否成功, 消息)
    """
    # 获取SMTP配置
    settings = await get_smtp_settings()
    
    smtp_server = settings.get('server', '')
    smtp_port = int(settings.get('port', 587))
    smtp_user = settings.get('user', '')
    smtp_password = settings.get('password', '')
    smtp_from = settings.get('from', '') or smtp_user
    
    # 根据端口自动判断加密方式
    use_tls, use_ssl = get_encryption_by_port(smtp_port)
    
    if not smtp_server or not smtp_user or not smtp_password:
        logger.warning("SMTP配置不完整，无法发送邮件")
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
    
    return send_email_sync(
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


async def send_test_email(to_email: str) -> tuple[bool, str]:
    """
    发送测试邮件
    返回: (是否成功, 消息)
    """
    # 获取SMTP配置
    settings = await get_smtp_settings()
    
    smtp_server = settings.get('server', '')
    smtp_port = int(settings.get('port', 587))
    smtp_user = settings.get('user', '')
    smtp_password = settings.get('password', '')
    smtp_from = settings.get('from', '') or smtp_user
    
    # 根据端口自动判断加密方式
    use_tls, use_ssl = get_encryption_by_port(smtp_port)
    
    if not smtp_server or not smtp_user or not smtp_password:
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
    
    return send_email_sync(
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
    import os
    from app.services.settlement_service import get_withdraw_notify_email
    
    # 从系统设置获取提现通知邮箱
    to_email = await get_withdraw_notify_email()
    if not to_email:
        logger.warning("系统未配置提现通知邮箱，无法发送提现通知")
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
        return False, "邮件服务未配置"
    
    
    # 生成审核链接
    from app.services.settlement_service import generate_review_token
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
        from app.services.withdraw_risk_check import run_all_checks
        risk_result = await run_all_checks(user_id, balance_after, record_id)
        risk_html = _build_risk_html(risk_result)
    except Exception as e:
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
    
    return send_email_sync(
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
