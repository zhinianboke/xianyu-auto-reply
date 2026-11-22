"""
SMTP 公共配置与发送服务。

功能：
1. 从统一数据库会话工厂读取 SMTP 配置
2. 按端口确定加密方式并诊断常见连接配置
3. 发送真实邮件并返回投递结果，供各邮件入口复用
"""
from __future__ import annotations

import email.charset
import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

from loguru import logger
from sqlalchemy import text

from common.db.session import async_session_maker


async def get_smtp_settings() -> dict:
    """从统一会话工厂读取 SMTP 配置，无参数，返回配置键值字典。"""
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

    Args:
        port: SMTP 服务端端口。
    Returns:
        是否使用 STARTTLS 与隐式 SSL。
    """
    if port in (465, 994):
        return False, True  # SSL
    elif port == 587:
        return True, False  # TLS (STARTTLS)
    else:
        return False, False  # 无加密 (端口25等)


def _diagnose_smtp_config(smtp_server: str, smtp_port: int) -> str | None:
    """
    根据服务器域名和端口给出常见错误诊断
    Args:
        smtp_server: SMTP 服务端域名。
        smtp_port: SMTP 服务端端口。
    Returns:
        中文配置诊断提示；None 表示未发现已知配置问题。
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
    if 'qq.com' in server_lower and smtp_port == 587:
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
    smtp_from: str | None = None,
    use_tls: bool = True,
    use_ssl: bool = False,
) -> tuple[bool, str]:
    """
    同步发送真实邮件，不记录数据库发送审计，由业务入口负责。

    Args:
        to_email: 收件邮箱。
        subject: 邮件主题。
        content: 邮件 HTML 正文。
        smtp_server/smtp_port: SMTP 主机与端口。
        smtp_user/smtp_password: SMTP 账号与密码。
        smtp_from: 发件人名称。
        use_tls/use_ssl: 是否使用 STARTTLS 或隐式 SSL。
    Returns:
        (是否真实发送成功, 中文发送结果)。
    """
    server = None
    # 当前执行到哪一步（用于错误诊断）
    stage = "初始化"
    try:
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
        msg['Message-ID'] = f"<{smtp_user.replace('@', '.')}.{int(time.time())}@mail>"

        # 添加纯文本版本（提高送达率）
        text_content = content.replace('<br>', '\n').replace('</p>', '\n')
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
        except Exception as exc:  # noqa: BLE001 - 投递已成功，退出失败仅记录而不改写发送结果
            logger.opt(exception=exc).warning("邮件已投递，但 SMTP 退出失败：to={}", to_email)

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
        return False, f"邮件发送失败（{stage}）: {type(e).__name__}: {e!s}"
    except (OSError, TimeoutError) as e:
        logger.error(f"SMTP网络异常 (stage={stage}): {type(e).__name__}: {e}")
        return False, f"SMTP 网络异常（{stage}）: {type(e).__name__}: {e!s}"
    except Exception as e:  # noqa: BLE001 - SMTP 边界完整记录异常并返回明确失败
        # 注意：避免用 f-string 把 str(e) 拼进 message 后再传给 loguru，
        # 因为 loguru 会对 message 调 str.format()，str(e) 中的 '{xxx}' 会被误认作占位符。
        # 使用 logger.opt(exception=e) 自动附带 traceback，参数走位置占位符 {} 安全。
        logger.opt(exception=e).error(
            "发送邮件失败 (stage={}): {}: {}",
            stage, type(e).__name__, str(e),
        )
        return False, f"发送邮件失败（{stage}）: {type(e).__name__}: {e!s}"
    finally:
        # 异常路径也确保连接关闭，避免文件句柄/socket 泄漏
        if server is not None:
            try:
                server.close()
            except Exception as exc:  # noqa: BLE001 - 必须记录 SMTP 连接关闭故障，保留真实投递结果
                logger.opt(exception=exc).warning("SMTP 连接关闭失败：to={}", to_email)
