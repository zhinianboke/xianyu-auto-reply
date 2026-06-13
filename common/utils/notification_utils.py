"""
通知工具函数

提供各种通知渠道的发送功能
"""
from __future__ import annotations

import json
import hmac
import hashlib
import base64
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

from loguru import logger

from common.utils.http_pool import http_pool


def parse_notification_config(config) -> Dict[str, Any]:
    """解析通知配置数据
    
    Args:
        config: 配置数据（可以是字典、JSON字符串或普通字符串）
        
    Returns:
        配置字典
    """
    # 如果已经是字典，直接返回
    if isinstance(config, dict):
        return config
    
    # 尝试解析JSON字符串
    try:
        return json.loads(config)
    except (json.JSONDecodeError, TypeError):
        return {"config": config}


async def send_dingtalk_notification(config_data: Dict[str, Any], message: str, timeout: int = 15) -> bool:
    """发送钉钉通知
    
    Args:
        config_data: 配置数据，包含webhook_url和可选的secret
        message: 通知消息
        
    Returns:
        是否发送成功
    """
    try:
        webhook_url = config_data.get('webhook_url') or config_data.get('config', '')
        secret = config_data.get('secret', '')

        webhook_url = webhook_url.strip() if webhook_url else ''
        if not webhook_url:
            logger.warning("📱 钉钉通知配置为空")
            return False

        # 如果有加签密钥，生成签名
        if secret:
            timestamp = str(round(time.time() * 1000))
            secret_enc = secret.encode('utf-8')
            string_to_sign = f'{timestamp}\n{secret}'
            string_to_sign_enc = string_to_sign.encode('utf-8')
            hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
            sign = base64.b64encode(hmac_code).decode('utf-8')
            webhook_url += f'&timestamp={timestamp}&sign={sign}'

        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": "闲鱼自动回复通知",
                "text": message
            }
        }

        async with http_pool.post(webhook_url, json=data, timeout=timeout) as response:
            if response.status == 200:
                logger.info("📱 钉钉通知发送成功")
                return True
            else:
                logger.warning(f"📱 钉钉通知发送失败: {response.status}")
                return False

    except Exception as e:
        logger.error(f"📱 发送钉钉通知异常: {e}")
        return False


async def send_feishu_card(webhook_url: str, card_data: Dict[str, Any], timeout: int = 15) -> bool:
    """发送飞书交互卡片消息

    使用飞书 webhook 发送 interactive card 消息 (schema 2.0)。

    Args:
        webhook_url: 飞书 webhook 地址
        card_data: 飞书卡片 JSON 结构（由 FeishuCardBuilder 生成）
        timeout: 请求超时时间（秒）

    Returns:
        是否发送成功
    """
    try:
        if not webhook_url:
            logger.warning("📱 飞书卡片通知 - Webhook URL配置为空")
            return False

        data = {
            "msg_type": "interactive",
            "card": card_data,
        }

        async with http_pool.post(webhook_url, json=data, timeout=timeout) as response:
            if response.status == 200:
                response_text = await response.text()
                try:
                    response_json = json.loads(response_text)
                    if response_json.get('code') == 0:
                        logger.info("📱 飞书卡片通知发送成功")
                        return True
                    else:
                        logger.warning(f"📱 飞书卡片通知发送失败: {response_json.get('msg')}")
                        return False
                except json.JSONDecodeError:
                    logger.info("📱 飞书卡片通知发送成功")
                    return True
            else:
                logger.warning(f"📱 飞书卡片通知发送失败: HTTP {response.status}")
                return False

    except Exception as e:
        logger.error(f"📱 发送飞书卡片通知异常: {e}")
        return False


async def send_feishu_notification(config_data: Dict[str, Any], message: str, timeout: int = 15) -> bool:
    """发送飞书通知
    
    Args:
        config_data: 配置数据，包含webhook_url和可选的secret
        message: 通知消息
        
    Returns:
        是否发送成功
    """
    try:
        webhook_url = config_data.get('webhook_url', '')
        secret = config_data.get('secret', '')

        if not webhook_url:
            logger.warning("📱 飞书通知 - Webhook URL配置为空")
            return False

        timestamp = str(int(time.time()))
        sign = ""

        if secret:
            string_to_sign = f'{timestamp}\n{secret}'
            hmac_code = hmac.new(
                string_to_sign.encode('utf-8'),
                ''.encode('utf-8'),
                digestmod=hashlib.sha256
            ).digest()
            sign = base64.b64encode(hmac_code).decode('utf-8')

        data = {
            "msg_type": "text",
            "content": {"text": message},
            "timestamp": timestamp
        }

        if sign:
            data["sign"] = sign

        async with http_pool.post(webhook_url, json=data, timeout=timeout) as response:
            if response.status == 200:
                response_text = await response.text()
                try:
                    response_json = json.loads(response_text)
                    if response_json.get('code') == 0:
                        logger.info("📱 飞书通知发送成功")
                        return True
                    else:
                        logger.warning(f"📱 飞书通知发送失败: {response_json.get('msg')}")
                        return False
                except json.JSONDecodeError:
                    logger.info("📱 飞书通知发送成功")
                    return True
            else:
                logger.warning(f"📱 飞书通知发送失败: HTTP {response.status}")
                return False

    except Exception as e:
        logger.error(f"📱 发送飞书通知异常: {e}")
        return False



async def send_bark_notification(config_data: Dict[str, Any], message: str, timeout: int = 15) -> bool:
    """发送Bark通知"""
    try:
        server_url = config_data.get('server_url', 'https://api.day.app').rstrip('/')
        device_key = config_data.get('device_key', '')
        title = config_data.get('title', '闲鱼自动回复通知')
        sound = config_data.get('sound', 'default')
        icon = config_data.get('icon', '')
        group = config_data.get('group', 'xianyu')
        url = config_data.get('url', '')

        if not device_key:
            logger.warning("📱 Bark通知 - 设备密钥配置为空")
            return False

        api_url = f"{server_url}/push"
        data = {
            "device_key": device_key,
            "title": title,
            "body": message,
            "sound": sound,
            "group": group
        }
        if icon:
            data["icon"] = icon
        if url:
            data["url"] = url

        async with http_pool.post(api_url, json=data, timeout=timeout) as response:
            if response.status == 200:
                response_text = await response.text()
                try:
                    response_json = json.loads(response_text)
                    if response_json.get('code') == 200:
                        logger.info("📱 Bark通知发送成功")
                        return True
                except json.JSONDecodeError:
                    if 'success' in response_text.lower() or 'ok' in response_text.lower():
                        logger.info("📱 Bark通知发送成功")
                        return True
            logger.warning(f"📱 Bark通知发送失败: HTTP {response.status}")
            return False

    except Exception as e:
        logger.error(f"📱 发送Bark通知异常: {e}")
        return False


def _send_smtp_message_blocking(
    smtp_server: str,
    smtp_port: int,
    email_user: str,
    email_password: str,
    msg,
    smtp_use_tls: bool,
) -> None:
    """实际执行 SMTP 发送的阻塞函数（由 asyncio.to_thread 调度）

    分步抛出更明确的异常上下文，便于上层日志定位失败步骤；
    statefully 关闭连接，避免 server.quit() 异常掩盖原始错误。
    """
    import smtplib

    server = None
    step = "connect"
    try:
        # 1) 建立连接
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)

        # 2) EHLO（部分服务器要求显式 EHLO 才接受后续命令）
        step = "ehlo"
        server.ehlo()

        # 3) STARTTLS（仅非 465 端口且开启 TLS 时）
        if smtp_port != 465 and smtp_use_tls:
            step = "starttls"
            server.starttls()
            server.ehlo()

        # 4) 登录
        step = "login"
        server.login(email_user, email_password)

        # 5) 发送
        step = "send"
        server.send_message(msg)
    except Exception as exc:
        # 在异常对象上记录失败步骤，便于上层中文日志识别
        try:
            setattr(exc, "_smtp_step", step)
        except Exception:
            pass
        raise
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass


async def send_email_notification(
    config_data: Dict[str, Any],
    message: str,
    attachment_path: str = None
) -> bool:
    """发送邮件通知

    将阻塞的 smtplib 调用放到线程池中执行，避免阻塞 asyncio 事件循环；
    分步记录错误，区分认证失败、服务器主动断开、连接失败等情况；
    遇到 SMTPServerDisconnected 这种瞬态错误时尝试重试一次。
    """
    import asyncio
    import os
    import re
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.image import MIMEImage
    from email.mime.application import MIMEApplication

    try:
        smtp_server = (config_data.get('smtp_server') or '').strip()
        try:
            smtp_port = int(config_data.get('smtp_port', 587) or 587)
        except (TypeError, ValueError):
            logger.warning("📱 邮件通知 smtp_port 配置无效，跳过发送")
            return False
        email_user = (config_data.get('email_user') or '').strip()
        email_password = config_data.get('email_password') or ''
        recipient_email = (config_data.get('recipient_email') or '').strip()

        # 默认: 465 用 SSL, 587 用 STARTTLS, 25 不加密；显式 smtp_use_tls 可覆盖
        raw_use_tls = config_data.get('smtp_use_tls')
        if raw_use_tls is None:
            smtp_use_tls = (smtp_port == 587)
        else:
            smtp_use_tls = bool(raw_use_tls)

        if not all([smtp_server, email_user, email_password, recipient_email]):
            logger.warning("📱 邮件通知配置不完整")
            return False

        # 检查配置是否包含中文占位符或无效字符
        def is_valid_config(value: str) -> bool:
            """检查配置值是否有效（不包含中文或占位符）"""
            if not value:
                return False
            # 检查是否包含中文字符
            if re.search(r'[\u4e00-\u9fff]', value):
                return False
            # 检查是否是示例占位符
            if 'example' in value.lower() or '你的' in value or '接收' in value:
                return False
            return True

        # 验证邮箱配置
        if not is_valid_config(email_user) or not is_valid_config(recipient_email):
            logger.warning(f"📱 邮件配置包含无效值或占位符，跳过发送")
            return False

        msg = MIMEMultipart()
        msg['From'] = email_user
        msg['To'] = recipient_email
        msg['Subject'] = "闲鱼自动回复通知"
        msg.attach(MIMEText(message, 'plain', 'utf-8'))

        if attachment_path and os.path.exists(attachment_path):
            try:
                with open(attachment_path, 'rb') as f:
                    img_data = f.read()
                filename = os.path.basename(attachment_path)
                if attachment_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    img = MIMEImage(img_data)
                    img.add_header('Content-Disposition', 'attachment', filename=filename)
                    msg.attach(img)
                else:
                    attach = MIMEApplication(img_data)
                    attach.add_header('Content-Disposition', 'attachment', filename=filename)
                    msg.attach(attach)
            except Exception as e:
                logger.error(f"📱 添加邮件附件失败: {e}")

        # 阻塞 SMTP 调用放到线程池，避免阻塞事件循环
        # SMTPServerDisconnected 多为瞬态，允许一次重试
        last_exc: Optional[BaseException] = None
        for attempt in range(2):
            try:
                await asyncio.to_thread(
                    _send_smtp_message_blocking,
                    smtp_server,
                    smtp_port,
                    email_user,
                    email_password,
                    msg,
                    smtp_use_tls,
                )
                logger.info(f"📱 邮件通知发送成功: {recipient_email}")
                return True
            except smtplib.SMTPServerDisconnected as exc:
                last_exc = exc
                step = getattr(exc, "_smtp_step", "unknown")
                if attempt == 0:
                    logger.warning(
                        f"📱 邮件服务器在[{step}]步骤主动断开连接，准备重试一次: {exc}"
                    )
                    await asyncio.sleep(1)
                    continue
                logger.error(
                    f"📱 邮件服务器在[{step}]步骤连接被关闭: {exc}; "
                    f"请确认 SMTP 端口与加密方式匹配 "
                    f"(465=SSL, 587=STARTTLS, 25=不加密)，"
                    f"以及邮箱是否开启 SMTP 服务、授权码是否正确"
                )
                return False
            except smtplib.SMTPAuthenticationError as exc:
                logger.error(
                    f"📱 邮件通知认证失败: {exc}; "
                    f"请检查邮箱用户名与授权码是否正确（多数邮箱要求使用授权码而非登录密码）"
                )
                return False
            except smtplib.SMTPConnectError as exc:
                logger.error(
                    f"📱 邮件服务器连接失败: {exc}; "
                    f"请检查 smtp_server={smtp_server!r}, smtp_port={smtp_port} 是否可达"
                )
                return False
            except smtplib.SMTPException as exc:
                step = getattr(exc, "_smtp_step", "unknown")
                logger.error(f"📱 SMTP 协议错误[{step}]: {exc}")
                return False
            except (OSError, TimeoutError) as exc:
                step = getattr(exc, "_smtp_step", "unknown")
                logger.error(f"📱 邮件网络错误[{step}]: {exc}")
                return False
        # 理论上不会走到这里
        if last_exc is not None:
            logger.error(f"📱 发送邮件通知重试后仍失败: {last_exc}")
        return False

    except Exception as e:
        logger.error(f"📱 发送邮件通知异常: {e}")
        return False


async def send_webhook_notification(config_data: Dict[str, Any], message: str, timeout: int = 15) -> bool:
    """发送Webhook通知"""
    try:
        webhook_url = config_data.get('webhook_url', '')
        http_method = config_data.get('http_method', 'POST').upper()
        headers_str = config_data.get('headers', '{}')

        if not webhook_url:
            logger.warning("📱 Webhook通知配置为空")
            return False

        try:
            custom_headers = json.loads(headers_str) if headers_str else {}
        except json.JSONDecodeError:
            custom_headers = {}

        headers = {'Content-Type': 'application/json'}
        headers.update(custom_headers)

        data = {
            'message': message,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'source': 'xianyu-auto-reply'
        }

        if http_method == 'POST':
            async with http_pool.post(webhook_url, json=data, headers=headers, timeout=timeout) as response:
                if response.status == 200:
                    logger.info("📱 Webhook通知发送成功")
                    return True
        elif http_method == 'PUT':
            async with http_pool.put(webhook_url, json=data, headers=headers, timeout=timeout) as response:
                if response.status == 200:
                    logger.info("📱 Webhook通知发送成功")
                    return True
        
        logger.warning(f"📱 Webhook通知发送失败")
        return False

    except Exception as e:
        logger.error(f"📱 发送Webhook通知异常: {e}")
        return False


async def send_wechat_notification(config_data: Dict[str, Any], message: str, timeout: int = 15) -> bool:
    """发送微信通知"""
    try:
        webhook_url = config_data.get('webhook_url', '')
        if not webhook_url:
            logger.warning("📱 微信通知配置为空")
            return False

        data = {
            "msgtype": "text",
            "text": {"content": message}
        }

        async with http_pool.post(webhook_url, json=data, timeout=timeout) as response:
            if response.status == 200:
                logger.info("📱 微信通知发送成功")
                return True
            logger.warning(f"📱 微信通知发送失败: {response.status}")
            return False

    except Exception as e:
        logger.error(f"📱 发送微信通知异常: {e}")
        return False


async def send_telegram_notification(config_data: Dict[str, Any], message: str, timeout: int = 15) -> bool:
    """发送Telegram通知"""
    try:
        bot_token = config_data.get('bot_token', '')
        chat_id = config_data.get('chat_id', '')

        if not all([bot_token, chat_id]):
            logger.warning("📱 Telegram通知配置不完整")
            return False

        api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }

        async with http_pool.post(api_url, json=data, timeout=timeout) as response:
            if response.status == 200:
                logger.info("📱 Telegram通知发送成功")
                return True
            logger.warning(f"📱 Telegram通知发送失败: {response.status}")
            return False

    except Exception as e:
        logger.error(f"📱 发送Telegram通知异常: {e}")
        return False
