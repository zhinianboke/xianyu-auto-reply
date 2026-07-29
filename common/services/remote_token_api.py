"""
远程闲鱼 Token 接口客户端。

功能：
1. 读取系统设置中的远程 Token 接口地址和接口秘钥
2. 按约定使用 X-API-Key 请求头调用远程接口
3. 统一校验远程接口返回的 token、device_id 字段（api_mode 为可选字段，缺失不校验）
4. 同时提供异步和同步调用入口，供主流程与滑块线程复用
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import aiohttp
import requests
from sqlalchemy import select

from common.db.compat import db_manager
from common.db.session import async_session_maker
from common.models.system_setting import SystemSetting


TOKEN_REMOTE_URL_SETTING_KEY = "token.remote_url"
TOKEN_REMOTE_SECRET_KEY_SETTING_KEY = "token.remote_secret_key"
REMOTE_TOKEN_TYPE = "xianyu_token"


@dataclass(frozen=True, slots=True)
class RemoteTokenSettings:
    """远程 Token 接口配置。"""

    url: str
    secret_key: str


@dataclass(frozen=True, slots=True)
class RemoteTokenResult:
    """远程 Token 接口响应结果。"""

    success: bool
    message: str
    response_json: Any
    status_code: int
    duration_seconds: float
    token: str = ""
    device_id: str = ""
    api_mode: str = ""


def validate_remote_token_settings(url: str, secret_key: str) -> str | None:
    """校验远程 Token 接口配置。

    Args:
        url: 远程接口 URL。
        secret_key: 接口秘钥，会作为 X-API-Key 请求头发送。
    Returns:
        校验通过返回 None，否则返回中文错误信息。
    """
    clean_url = str(url or "").strip()
    clean_secret_key = str(secret_key or "").strip()
    if not clean_url:
        return "请选择远程接口时必须填写远程URL"
    if not clean_secret_key:
        return "请选择远程接口时必须填写秘钥"

    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "远程URL格式无效，请填写以 http:// 或 https:// 开头的完整地址"
    return None


async def load_remote_token_settings() -> RemoteTokenSettings:
    """异步读取远程 Token 接口配置。

    Returns:
        远程接口配置对象；未配置时字段为空字符串。
    """
    keys = (
        TOKEN_REMOTE_URL_SETTING_KEY,
        TOKEN_REMOTE_SECRET_KEY_SETTING_KEY,
    )
    async with async_session_maker() as session:
        result = await session.execute(
            select(SystemSetting.key, SystemSetting.value).where(SystemSetting.key.in_(keys))
        )
        settings = {key: value for key, value in result.all()}
    return RemoteTokenSettings(
        url=str(settings.get(TOKEN_REMOTE_URL_SETTING_KEY) or "").strip(),
        secret_key=str(
            settings.get(TOKEN_REMOTE_SECRET_KEY_SETTING_KEY) or ""
        ).strip(),
    )


def load_remote_token_settings_sync() -> RemoteTokenSettings:
    """同步读取远程 Token 接口配置。

    Returns:
        远程接口配置对象；未配置时字段为空字符串。
    """
    return RemoteTokenSettings(
        url=str(db_manager.get_system_setting(TOKEN_REMOTE_URL_SETTING_KEY, "") or "").strip(),
        secret_key=str(
            db_manager.get_system_setting(TOKEN_REMOTE_SECRET_KEY_SETTING_KEY, "") or ""
        ).strip(),
    )


def _build_remote_token_payload(cookies: str) -> dict[str, Any]:
    """构造远程接口请求体。

    Args:
        cookies: 浏览器复制的完整闲鱼 Cookie 字符串，放入 data.cookies 传给远程接口。
    Returns:
        符合远程接口约定的请求体：{"type": ..., "data": {"cookies": ...}}。
    """
    return {
        "type": REMOTE_TOKEN_TYPE,
        "data": {
            "cookies": str(cookies or ""),
        },
    }


def _parse_remote_token_response(
    response_json: Any,
    status_code: int,
    duration_seconds: float,
) -> RemoteTokenResult:
    """解析远程接口响应并转换为统一结果。"""
    if not isinstance(response_json, dict):
        return RemoteTokenResult(
            success=False,
            message="远程接口返回格式无效，响应不是JSON对象",
            response_json=response_json,
            status_code=status_code,
            duration_seconds=duration_seconds,
        )

    message = str(response_json.get("message") or "")
    if not bool(response_json.get("success")):
        return RemoteTokenResult(
            success=False,
            message=message or "远程接口返回失败",
            response_json=response_json,
            status_code=status_code,
            duration_seconds=duration_seconds,
        )

    data = response_json.get("data")
    if not isinstance(data, dict):
        return RemoteTokenResult(
            success=False,
            message="远程接口返回成功但缺少data对象",
            response_json=response_json,
            status_code=status_code,
            duration_seconds=duration_seconds,
        )

    token = str(data.get("token") or "").strip()
    device_id = str(data.get("device_id") or "").strip()
    api_mode = str(data.get("api_mode") or "").strip()
    if not token:
        return RemoteTokenResult(
            success=False,
            message="远程接口返回成功但缺少token",
            response_json=response_json,
            status_code=status_code,
            duration_seconds=duration_seconds,
        )
    if not device_id:
        return RemoteTokenResult(
            success=False,
            message="远程接口返回成功但缺少device_id",
            response_json=response_json,
            status_code=status_code,
            duration_seconds=duration_seconds,
        )
    # api_mode 为远程接口可选返回字段，缺失时不再校验，保持空字符串由下游兜底展示

    return RemoteTokenResult(
        success=True,
        message=message or "远程接口取Token成功",
        response_json=response_json,
        status_code=status_code,
        duration_seconds=duration_seconds,
        token=token,
        device_id=device_id,
        api_mode=api_mode,
    )


async def request_remote_xianyu_token(
    url: str,
    secret_key: str,
    *,
    cookies: str = "",
    timeout_seconds: int = 30,
) -> RemoteTokenResult:
    """异步调用远程 Token 接口。

    Args:
        url: 远程接口 URL。
        secret_key: 接口秘钥，会作为 X-API-Key 请求头发送。
        cookies: 浏览器复制的完整闲鱼 Cookie 字符串，放入请求体 data.cookies。
        timeout_seconds: 请求总超时时间。
    Returns:
        远程接口调用结果。
    """
    error_message = validate_remote_token_settings(url, secret_key)
    if error_message:
        return RemoteTokenResult(
            success=False,
            message=error_message,
            response_json=None,
            status_code=0,
            duration_seconds=0,
        )

    started_at = time.time()
    async with aiohttp.ClientSession() as session:
        async with session.post(
            str(url).strip(),
            json=_build_remote_token_payload(cookies),
            headers={"X-API-Key": str(secret_key).strip()},
            timeout=aiohttp.ClientTimeout(total=timeout_seconds),
        ) as response:
            response_json = await response.json(content_type=None)
            return _parse_remote_token_response(
                response_json,
                response.status,
                time.time() - started_at,
            )


async def request_remote_xianyu_token_from_settings(
    *,
    cookies: str = "",
    timeout_seconds: int = 30,
) -> RemoteTokenResult:
    """从系统设置读取配置并异步调用远程 Token 接口。"""
    settings = await load_remote_token_settings()
    return await request_remote_xianyu_token(
        settings.url,
        settings.secret_key,
        cookies=cookies,
        timeout_seconds=timeout_seconds,
    )


def request_remote_xianyu_token_sync(
    url: str,
    secret_key: str,
    *,
    cookies: str = "",
    timeout_seconds: float = 10,
) -> RemoteTokenResult:
    """同步调用远程 Token 接口。

    Args:
        url: 远程接口 URL。
        secret_key: 接口秘钥，会作为 X-API-Key 请求头发送。
        cookies: 浏览器复制的完整闲鱼 Cookie 字符串，放入请求体 data.cookies。
        timeout_seconds: 请求总超时时间。
    Returns:
        远程接口调用结果。
    """
    error_message = validate_remote_token_settings(url, secret_key)
    if error_message:
        return RemoteTokenResult(
            success=False,
            message=error_message,
            response_json=None,
            status_code=0,
            duration_seconds=0,
        )

    started_at = time.time()
    response = requests.post(
        str(url).strip(),
        json=_build_remote_token_payload(cookies),
        headers={"X-API-Key": str(secret_key).strip()},
        timeout=timeout_seconds,
    )
    return _parse_remote_token_response(
        response.json(),
        response.status_code,
        time.time() - started_at,
    )


def request_remote_xianyu_token_from_settings_sync(
    *,
    cookies: str = "",
    timeout_seconds: float = 10,
) -> RemoteTokenResult:
    """从系统设置读取配置并同步调用远程 Token 接口。"""
    settings = load_remote_token_settings_sync()
    return request_remote_xianyu_token_sync(
        settings.url,
        settings.secret_key,
        cookies=cookies,
        timeout_seconds=timeout_seconds,
    )
