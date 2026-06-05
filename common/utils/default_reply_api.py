"""默认回复 API 类型公共工具

职责（被后端保存校验、websocket 运行时调用共同复用，避免重复实现）：
1. 校验用户填写的 API 地址合法性，并防范 SSRF（禁止指向内网/回环地址）。
2. 调用外部 API（POST），将消息内容传给对方接口。
3. 解析对方返回内容：兼容 JSON（{"reply": "..."} / {"success", "reply"}）与纯文本两种格式。
"""
from __future__ import annotations

import ipaddress
import json
import socket
from typing import Optional, Tuple
from urllib.parse import urlparse

import aiohttp
from loguru import logger

# API 默认超时时间（秒）
DEFAULT_API_TIMEOUT = 80
# 超时时间允许范围（秒）
MIN_API_TIMEOUT = 1
MAX_API_TIMEOUT = 120


def validate_api_url(api_url: str) -> Tuple[bool, str]:
    """校验默认回复 API 地址是否合法且安全（防 SSRF）。

    Args:
        api_url: 用户填写的 API 地址

    Returns:
        (是否合法, 错误消息)。合法时错误消息为空字符串。
    """
    if not api_url or not api_url.strip():
        return False, "API地址不能为空"

    url = api_url.strip()
    parsed = urlparse(url)

    # 仅允许 http / https
    if parsed.scheme not in ("http", "https"):
        return False, "API地址必须以 http:// 或 https:// 开头"

    host = parsed.hostname
    if not host:
        return False, "API地址缺少主机名"

    # 解析主机名对应的所有 IP，逐个校验是否为内网/回环/保留地址
    try:
        addr_infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # 域名无法解析：保存阶段不强制拦截（可能保存时网络不可达），
        # 真正调用时再行兜底处理。但格式本身合法，放行。
        return True, ""

    for info in addr_infos:
        ip_str = info[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
            or ip_obj.is_unspecified
        ):
            return False, "API地址不允许指向内网或回环地址"

    return True, ""


def normalize_api_timeout(timeout: Optional[int]) -> int:
    """将超时时间归一到合法范围，非法时回退默认值。"""
    if timeout is None:
        return DEFAULT_API_TIMEOUT
    try:
        value = int(timeout)
    except (TypeError, ValueError):
        return DEFAULT_API_TIMEOUT
    if value < MIN_API_TIMEOUT:
        return MIN_API_TIMEOUT
    if value > MAX_API_TIMEOUT:
        return MAX_API_TIMEOUT
    return value


def parse_api_reply(status: int, body_text: str) -> Optional[str]:
    """解析外部 API 的返回内容，提取要发送给买家的文本。

    兼容两种格式：
    1. JSON：``{"success": true, "reply": "..."}`` 或 ``{"reply": "..."}``、``{"data": "..."}``
       - 含 success 字段且为 false 时视为失败，返回 None
    2. 纯文本：整个响应体即为要发送的内容

    Args:
        status: HTTP 状态码
        body_text: 响应体文本

    Returns:
        要发送的文本；无有效内容或失败时返回 None
    """
    if status != 200:
        logger.warning(f"默认回复API返回非200状态码: {status}")
        return None

    if body_text is None:
        return None

    text = body_text.strip()
    if not text:
        return None

    # 优先尝试 JSON 解析
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        data = None

    if isinstance(data, dict):
        # 含 success 字段且明确为 False，视为业务失败
        if "success" in data and not data.get("success"):
            logger.warning(f"默认回复API返回失败标志: {data.get('message') or data}")
            return None
        # 依次尝试常见字段
        for key in ("reply", "data", "content", "message"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    if isinstance(data, str) and data.strip():
        # JSON 字符串字面量
        return data.strip()

    # 非 JSON，按纯文本处理
    return text


async def call_reply_api(
    account_id: str,
    message: str,
    api_url: str,
    timeout: Optional[int] = DEFAULT_API_TIMEOUT,
) -> Optional[str]:
    """调用外部 API 获取默认回复内容。

    POST 请求体: ``{"account_id": "...", "message": "..."}``

    Args:
        account_id: 闲鱼账号标识
        message: 买家发来的消息内容
        api_url: 外部 API 地址
        timeout: 请求超时时间（秒）

    Returns:
        外部 API 返回的回复文本；失败/超时/无内容时返回 None
    """
    valid, err = validate_api_url(api_url)
    if not valid:
        logger.warning(f"【{account_id}】默认回复API地址非法，跳过调用: {err}")
        return None

    timeout_seconds = normalize_api_timeout(timeout)
    payload = {"account_id": account_id, "message": message}

    try:
        client_timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            # 禁止自动跟随重定向：防止外部域名通过 30x 跳转到内网/回环地址
            # （如云元数据 169.254.169.254）绕过保存时的 SSRF 地址校验。
            async with session.post(
                api_url.strip(), json=payload, allow_redirects=False
            ) as response:
                # 命中重定向直接视为非法响应，不发送任何回复
                if response.status in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location", "")
                    logger.warning(
                        f"【{account_id}】默认回复API返回重定向({response.status})，"
                        f"为防 SSRF 已拒绝跟随: {location}"
                    )
                    return None
                body_text = await response.text()
                reply = parse_api_reply(response.status, body_text)
                if reply:
                    logger.info(f"【{account_id}】默认回复API调用成功，返回内容长度: {len(reply)}")
                else:
                    logger.info(f"【{account_id}】默认回复API未返回有效内容")
                return reply
    except aiohttp.ClientError as exc:
        logger.warning(f"【{account_id}】默认回复API网络请求失败: {exc}")
        return None
    except Exception as exc:
        logger.warning(f"【{account_id}】默认回复API调用异常: {exc}")
        return None
