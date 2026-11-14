"""HTTP通知渠道发送、响应业务状态校验与历史配置兼容。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict
from urllib.parse import quote

import aiohttp
from loguru import logger

from common.utils.time_utils import get_beijing_now_naive


async def _response_succeeded(response, channel: str, field: str, expected: object, request_body: dict) -> bool:
    """检查HTTP和渠道业务码；无效JSON或缺失状态字段均按失败处理。"""
    body = await response.text()
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        payload = None
    ok = (
        response.status == 200 and isinstance(payload, dict)
        and type(payload.get(field)) is type(expected) and payload.get(field) == expected
    )
    if ok:
        logger.info("通知发送成功：channel={}", channel)
    else:
        logger.error(
            "通知发送失败：channel={}, method={}, url={}, request_headers={}, request_body={}, status={}, response_headers={}, response_body={}",
            channel, response.request_info.method, str(response.request_info.real_url),
            dict(response.request_info.headers), request_body, response.status, dict(response.headers), body,
        )
    return ok


async def send_dingtalk_notification(config_data: Dict[str, Any], message: str) -> bool:
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
            sign = quote(base64.b64encode(hmac_code).decode('utf-8'), safe='')
            separator = '&' if '?' in webhook_url else '?'
            webhook_url += f'{separator}timestamp={timestamp}&sign={sign}'

        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": "闲鱼自动回复通知",
                "text": message
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=data, timeout=10) as response:
                return await _response_succeeded(response, "钉钉", "errcode", 0, data)

    except Exception as e:
        logger.error(f"📱 发送钉钉通知异常: {e}")
        return False


async def send_feishu_notification(config_data: Dict[str, Any], message: str) -> bool:
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

        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=data, timeout=10) as response:
                return await _response_succeeded(response, "飞书", "code", 0, data)

    except Exception as e:
        logger.error(f"📱 发送飞书通知异常: {e}")
        return False



async def send_bark_notification(config_data: Dict[str, Any], message: str) -> bool:
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

        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=data, timeout=10) as response:
                return await _response_succeeded(response, "Bark", "code", 200, data)

    except Exception as e:
        logger.error(f"📱 发送Bark通知异常: {e}")
        return False


async def send_webhook_notification(config_data: Dict[str, Any], message: str) -> bool:
    """发送自定义Webhook；兼容对象/JSON字符串请求头及历史method字段。"""
    try:
        webhook_url = config_data.get("webhook_url", "")
        http_method = str(config_data.get("http_method") or config_data.get("method") or "POST").upper()
        if not webhook_url:
            raise ValueError("Webhook地址不能为空")
        if http_method not in ("POST", "PUT"):
            raise ValueError("Webhook请求方法只支持POST或PUT")
        raw_headers = config_data.get("headers", {})
        custom_headers = json.loads(raw_headers) if isinstance(raw_headers, str) and raw_headers.strip() else (raw_headers or {})
        if not isinstance(custom_headers, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in custom_headers.items()
        ):
            raise ValueError("Webhook请求头必须为字符串键值组成的JSON对象")
        headers = {"Content-Type": "application/json", **custom_headers}
        data = {
            "message": message,
            "timestamp": get_beijing_now_naive().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "xianyu-auto-reply",
        }
        async with aiohttp.ClientSession() as session:
            async with session.request(http_method, webhook_url, json=data, headers=headers, timeout=10) as response:
                body = await response.text()
                if 200 <= response.status < 300:
                    logger.info("Webhook通知发送成功")
                    return True
                logger.error(
                    "Webhook通知发送失败：method={}, url={}, request_headers={}, request_body={}, status={}, response_headers={}, response_body={}",
                    http_method, webhook_url, dict(response.request_info.headers), data,
                    response.status, dict(response.headers), body,
                )
        return False
    except Exception:
        logger.exception("Webhook通知发送异常")
        return False


async def send_wechat_notification(config_data: Dict[str, Any], message: str) -> bool:
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

        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=data, timeout=10) as response:
                return await _response_succeeded(response, "企业微信", "errcode", 0, data)

    except Exception as e:
        logger.error(f"📱 发送微信通知异常: {e}")
        return False


async def send_pushplus_notification(config_data: Dict[str, Any], message: str) -> bool:
    """发送PushPlus通知

    Args:
        config_data: 配置数据，包含token，可选topic、template、title
        message: 通知消息

    Returns:
        是否发送成功
    """
    try:
        token = (config_data.get('token') or '').strip()
        if not token:
            logger.warning("📱 PushPlus通知 - token配置为空")
            return False

        title = config_data.get('title') or '闲鱼自动回复通知'
        template = config_data.get('template') or 'txt'
        topic = (config_data.get('topic') or '').strip()
        server_url = (config_data.get('server_url') or 'https://www.pushplus.plus').rstrip('/')

        api_url = f"{server_url}/send"
        data = {
            "token": token,
            "title": title,
            "content": message,
            "template": template,
        }
        if topic:
            data["topic"] = topic

        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=data, timeout=10) as response:
                return await _response_succeeded(response, "PushPlus", "code", 200, data)

    except Exception as e:
        logger.error(f"📱 发送PushPlus通知异常: {e}")
        return False


async def send_telegram_notification(config_data: Dict[str, Any], message: str) -> bool:
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
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=data, timeout=10) as response:
                return await _response_succeeded(response, "Telegram", "ok", True, data)

    except Exception as e:
        logger.error(f"📱 发送Telegram通知异常: {e}")
        return False
