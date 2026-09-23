"""远程位置消息接口客户端。

运行时只向远程服务请求完整位置消息报文并返回 ``data.message``；
个人设置中的测试接口另使用固定测试向量验证远程服务连通性。
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import ipaddress
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import aiohttp
from common.utils.xianyu_utils import generate_mid, generate_uuid

LOCATION_PROTOCOL_VERSION = "xianyu-location-envelope-v1"
REMOTE_LOCATION_MESSAGE_TYPE = "xianyu_location_message"
# Keep the legacy test marker for compatibility with existing fixtures, while
# accepting the actual LWP operation used by the local Xianyu senders.
LOCATION_MESSAGE_LWP = "LWP"
LOCATION_MESSAGE_SEND_LWP = "/r/MessageSend/sendByReceiverScope"
TEST_CHAT_ID = "location-test-chat"
TEST_RECEIVER_ID = "location-test-receiver"
TEST_SENDER_ID = "location-test-sender"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REMOTE_LOCATION_TIMEOUT_SECONDS = 15
REMOTE_LOCATION_CONNECT_TIMEOUT_SECONDS = 8
ALLOWED_PORTS = frozenset({80, 443})


@dataclass(frozen=True, slots=True)
class RemoteLocationMessageTestResult:
    """位置消息远程接口测试结果。"""

    success: bool
    message: str
    status_code: int = 0
    duration_ms: int = 0
    protocol_version: str = ""


class RemoteLocationMessageError(RuntimeError):
    """远程位置消息接口调用失败。"""


def _strip_goofish_suffix(value: str) -> str:
    """接口参数要求使用不带 ``@goofish`` 后缀的 ID。"""
    text = str(value or "").strip()
    return text[:-8] if text.lower().endswith("@goofish") else text


async def fetch_remote_location_message(
    *,
    url: str,
    secret_key: str,
    chat_id: str,
    send_user_id: str,
    sender_user_id: str,
    longitude: str,
    latitude: str,
    title: str,
    subtitle: str = "",
    timeout_seconds: float = REMOTE_LOCATION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """调用远程接口并返回 ``data.message``，不在本地构造 LWP 报文。"""
    try:
        validate_remote_location_settings(url, secret_key)
    except ValueError as exc:
        raise RemoteLocationMessageError(str(exc)) from exc

    clean_url = str(url or "").strip()
    clean_secret = str(secret_key or "").strip()
    try:
        parsed = urlsplit(clean_url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = await _resolve_public_addresses(parsed.hostname or "", port)
        target_url, host_header = _url_for_address(parsed, addresses[0], port)
    except Exception as exc:  # noqa: BLE001
        raise RemoteLocationMessageError(
            f"无法连接远程位置消息接口: {type(exc).__name__}: {_redact_secret(str(exc), clean_secret)}"
        ) from exc
    location: dict[str, str] = {
        "longitude": str(longitude or "").strip(),
        "latitude": str(latitude or "").strip(),
        "title": str(title or "").strip(),
    }
    clean_subtitle = str(subtitle or "").strip()
    if clean_subtitle:
        location["subtitle"] = clean_subtitle

    payload: dict[str, Any] = {
        "type": REMOTE_LOCATION_MESSAGE_TYPE,
        "data": {
            "protocol_version": LOCATION_PROTOCOL_VERSION,
            # 闲鱼 WebSocket 的真实发送帧使用项目统一的 mid/uuid 生成规则：
            # mid 为 ``<随机前缀><毫秒时间戳> 0``，uuid 为 ``-<毫秒时间戳>1``。
            # 这些标识只作为远程接口请求参数，消息正文仍完全由远程服务返回。
            "mid": generate_mid(),
            "uuid": generate_uuid(),
            "chat_id": _strip_goofish_suffix(chat_id),
            "send_user_id": _strip_goofish_suffix(send_user_id),
            "sender_user_id": _strip_goofish_suffix(sender_user_id),
            "location": location,
        },
    }
    timeout = aiohttp.ClientTimeout(total=float(timeout_seconds))
    headers = {
        "X-API-Key": clean_secret,
        "Content-Type": "application/json",
        "Host": host_header,
    }
    started = time.perf_counter()
    try:
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            request_kwargs: dict[str, Any] = {
                "json": payload,
                "headers": headers,
                "allow_redirects": False,
            }
            if parsed.scheme == "https":
                request_kwargs.update({"ssl": True, "server_hostname": parsed.hostname})
            async with session.post(target_url, **request_kwargs) as response:
                status_code = response.status
                raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
    except Exception as exc:  # noqa: BLE001
        raise RemoteLocationMessageError(
            f"无法连接远程位置消息接口: {type(exc).__name__}: {_redact_secret(str(exc), clean_secret)}"
        ) from exc

    if len(raw) > MAX_RESPONSE_BYTES:
        raise RemoteLocationMessageError("远程接口响应内容过大")
    if status_code < 200 or status_code >= 300:
        raise RemoteLocationMessageError(f"远程接口返回异常 (HTTP {status_code})")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RemoteLocationMessageError("远程接口响应不是有效的 UTF-8 JSON") from exc
    if not isinstance(body, dict):
        raise RemoteLocationMessageError("远程接口响应格式不正确")
    if body.get("success") is not True:
        message = _redact_secret(str(body.get("message") or ""), clean_secret)
        raise RemoteLocationMessageError(message or "远程接口处理失败")
    data = body.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("message"), dict) or not data["message"]:
        raise RemoteLocationMessageError("远程接口成功但缺少有效的 data.message")
    return {
        "message": data["message"],
        "mid": payload["data"]["mid"],
        "uuid": payload["data"]["uuid"],
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def _expected_location_card() -> dict[str, Any]:
    """返回固定测试向量对应的位置卡片。"""
    return {
        "locationCard": {
            "longitude": "0",
            "latitude": "0",
            "title": "位置消息接口测试",
            "subtitle": "0, 0",
        }
    }


def validate_remote_location_settings(url: str, secret_key: str) -> None:
    """校验 URL、端口和请求头秘钥格式，不执行网络请求。"""
    clean_url = str(url or "").strip()
    clean_secret = str(secret_key or "").strip()
    if not clean_url:
        raise ValueError("请填写远程URL")
    if not clean_secret:
        raise ValueError("请填写秘钥")
    if any(ord(char) < 32 or ord(char) == 127 for char in clean_secret):
        raise ValueError("秘钥格式无效，不能包含控制字符")

    parsed = urlsplit(clean_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("仅支持 HTTP 或 HTTPS 远程URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("远程URL不能包含用户名或密码")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("远程URL端口无效") from exc
    expected_port = 443 if parsed.scheme == "https" else 80
    if port is None:
        port = expected_port
    if port not in ALLOWED_PORTS:
        raise ValueError("远程URL仅允许使用 80 或 443 端口")
    if not parsed.hostname:
        raise ValueError("远程URL缺少主机名")


async def _resolve_public_addresses(host: str, port: int) -> tuple[str, ...]:
    """解析主机并拒绝非公网地址，降低 SSRF 风险。"""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            type=__import__("socket").SOCK_STREAM,
            proto=__import__("socket").IPPROTO_TCP,
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError("远程URL主机名解析失败") from exc

    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        address = str(sockaddr[0])
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError("远程URL解析出了无效IP地址") from exc
        # is_global 会同时排除回环、内网、链路本地、共享地址和保留地址。
        if not parsed.is_global:
            raise ValueError("远程URL解析到内网或回环地址，已拒绝连接")
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise ValueError("远程URL未解析到可用地址")
    return tuple(addresses)


def _url_for_address(parsed: SplitResult, address: str, port: int) -> tuple[str, str]:
    """将请求定向到已校验的 IP，同时保留原始 Host 头。"""
    original_host = parsed.netloc
    if ":" in address and not address.startswith("["):
        address = f"[{address}]"
    target = urlunsplit((parsed.scheme, f"{address}:{port}", parsed.path, parsed.query, ""))
    return target, original_host


def _redact_secret(message: str, secret_key: str) -> str:
    text = str(message or "")
    return text.replace(secret_key, "***") if secret_key else text


def _validate_response_message(message: Any, mid: str, message_uuid: str) -> str | None:
    """校验远程返回的完整位置 LWP 报文。"""
    if not isinstance(message, dict):
        return "远程接口返回的消息报文格式不正确"
    if message.get("lwp") not in {LOCATION_MESSAGE_LWP, LOCATION_MESSAGE_SEND_LWP}:
        return "位置消息报文 LWP 不匹配"
    headers = message.get("headers")
    if not isinstance(headers, dict) or headers.get("mid") != mid:
        return "位置消息报文 mid不匹配"
    body = message.get("body")
    if not isinstance(body, list) or len(body) < 2:
        return "位置消息报文 body 格式不正确"
    item = body[0]
    receivers = body[1]
    if not isinstance(item, dict) or item.get("uuid") != message_uuid:
        return "位置消息报文 uuid不匹配"
    if item.get("cid") != f"{TEST_CHAT_ID}@goofish":
        return "位置消息报文会话 ID 不匹配"
    content = item.get("content")
    custom = content.get("custom") if isinstance(content, dict) else None
    if not isinstance(content, dict) or content.get("contentType") != 101:
        return "位置消息报文内容类型不匹配"
    if not isinstance(custom, dict) or custom.get("type") != 30:
        return "位置消息报文自定义类型不匹配"
    encoded = custom.get("data")
    if not isinstance(encoded, str) or not encoded:
        return "位置消息报文位置卡片数据缺失"
    try:
        decoded = base64.b64decode(encoded, validate=True)
        card = json.loads(decoded.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return "位置消息报文位置卡片无法解析"
    if card != _expected_location_card():
        return "位置消息报文卡片内容不匹配"
    if not isinstance(receivers, dict):
        return "位置消息报文接收方信息不正确"
    expected = {f"{TEST_RECEIVER_ID}@goofish", f"{TEST_SENDER_ID}@goofish"}
    actual = receivers.get("actualReceivers")
    if not isinstance(actual, list) or not expected.issubset({str(item) for item in actual}):
        return "位置消息报文接收方不匹配"
    return None


async def test_remote_location_message_interface(
    url: str,
    secret_key: str,
) -> RemoteLocationMessageTestResult:
    """调用远程位置消息接口并验证固定测试向量。"""
    try:
        validate_remote_location_settings(url, secret_key)
    except ValueError as exc:
        return RemoteLocationMessageTestResult(False, str(exc))

    clean_url = str(url).strip()
    clean_secret = str(secret_key).strip()
    parsed = urlsplit(clean_url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    started = time.perf_counter()
    try:
        addresses = await _resolve_public_addresses(parsed.hostname or "", port)
        mid = f"location-test-{uuid.uuid4().hex}"
        message_uuid = str(uuid.uuid4())
        payload: dict[str, Any] = {
            "type": REMOTE_LOCATION_MESSAGE_TYPE,
            "data": {
                "protocol_version": LOCATION_PROTOCOL_VERSION,
                "mid": mid,
                "uuid": message_uuid,
                "chat_id": TEST_CHAT_ID,
                "send_user_id": TEST_RECEIVER_ID,
                "sender_user_id": TEST_SENDER_ID,
                "location": {
                    "longitude": "0",
                    "latitude": "0",
                    "title": "位置消息接口测试",
                    "subtitle": "0, 0",
                },
            },
        }
        target_url, host_header = _url_for_address(parsed, addresses[0], port)
        headers = {
            "X-API-Key": clean_secret,
            "Content-Type": "application/json",
            "Host": host_header,
        }
        timeout = aiohttp.ClientTimeout(
            total=REMOTE_LOCATION_TIMEOUT_SECONDS,
            connect=REMOTE_LOCATION_CONNECT_TIMEOUT_SECONDS,
        )
        # Keep TLS verification enabled for HTTPS.  The request is sent to the
        # already-resolved IP address to reduce DNS rebinding risk, so provide
        # the original hostname as the TLS SNI/certificate name.
        connector = aiohttp.TCPConnector()
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            request_kwargs: dict[str, Any] = {
                "json": payload,
                "headers": headers,
                "allow_redirects": False,
            }
            if parsed.scheme == "https":
                request_kwargs.update({"ssl": True, "server_hostname": parsed.hostname})
            async with session.post(target_url, **request_kwargs) as response:
                status_code = response.status
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        declared_length = int(content_length)
                    except ValueError:
                        declared_length = 0
                    if declared_length > MAX_RESPONSE_BYTES:
                        return RemoteLocationMessageTestResult(
                            False,
                            "远程接口响应内容过大",
                            status_code,
                            int((time.perf_counter() - started) * 1000),
                        )
                raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    return RemoteLocationMessageTestResult(
                        False,
                        "远程接口响应内容过大",
                        status_code,
                        int((time.perf_counter() - started) * 1000),
                    )
                if 300 <= status_code < 400:
                    return RemoteLocationMessageTestResult(
                        False,
                        "远程接口不允许重定向",
                        status_code,
                        int((time.perf_counter() - started) * 1000),
                    )
                try:
                    body = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return RemoteLocationMessageTestResult(
                        False,
                        "远程接口响应不是有效的UTF-8 JSON",
                        status_code,
                        int((time.perf_counter() - started) * 1000),
                    )
    except ValueError as exc:
        return RemoteLocationMessageTestResult(False, str(exc), 0, int((time.perf_counter() - started) * 1000))
    except Exception as exc:  # noqa: BLE001
        return RemoteLocationMessageTestResult(
            False,
            f"无法连接远程接口：{type(exc).__name__}: {_redact_secret(str(exc), clean_secret)}",
            0,
            int((time.perf_counter() - started) * 1000),
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    if status_code != 200:
        return RemoteLocationMessageTestResult(
            False,
            f"远程接口返回异常（HTTP {status_code}）",
            status_code,
            duration_ms,
        )
    if not isinstance(body, dict):
        return RemoteLocationMessageTestResult(False, "远程接口响应格式不正确", status_code, duration_ms)
    remote_message = str(body.get("message") or "").strip()
    if body.get("success") is not True:
        return RemoteLocationMessageTestResult(
            False,
            _redact_secret(remote_message, clean_secret) or "远程接口处理失败",
            status_code,
            duration_ms,
        )
    data = body.get("data")
    if not isinstance(data, dict):
        return RemoteLocationMessageTestResult(False, "远程接口成功但缺少 data 对象", status_code, duration_ms)
    if data.get("protocol_version") != LOCATION_PROTOCOL_VERSION:
        return RemoteLocationMessageTestResult(False, "位置消息协议版本不匹配", status_code, duration_ms)
    if data.get("mid") != mid:
        return RemoteLocationMessageTestResult(False, "位置消息报文 mid不匹配", status_code, duration_ms)
    if data.get("uuid") != message_uuid:
        return RemoteLocationMessageTestResult(False, "位置消息报文 uuid不匹配", status_code, duration_ms)
    validation_error = _validate_response_message(data.get("message"), mid, message_uuid)
    if validation_error:
        return RemoteLocationMessageTestResult(False, validation_error, status_code, duration_ms)
    return RemoteLocationMessageTestResult(
        True,
        "连接成功",
        status_code,
        duration_ms,
        LOCATION_PROTOCOL_VERSION,
    )


__all__ = [
    "ALLOWED_PORTS",
    "LOCATION_MESSAGE_LWP",
    "LOCATION_MESSAGE_SEND_LWP",
    "LOCATION_PROTOCOL_VERSION",
    "MAX_RESPONSE_BYTES",
    "REMOTE_LOCATION_MESSAGE_TYPE",
    "RemoteLocationMessageError",
    "RemoteLocationMessageTestResult",
    "TEST_CHAT_ID",
    "TEST_RECEIVER_ID",
    "TEST_SENDER_ID",
    "_expected_location_card",
    "_resolve_public_addresses",
    "fetch_remote_location_message",
    "test_remote_location_message_interface",
    "validate_remote_location_settings",
]
