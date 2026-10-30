"""
远程闲鱼 Token 接口客户端。

功能：
1. 按账号所属用户优先读取个人配置，未配置时读取系统配置
2. 按约定使用 X-API-Key 请求头调用远程接口
3. 统一校验远程接口返回的 token、device_id 字段（api_mode 为可选字段，缺失不校验）
4. 同时提供异步和同步调用入口，供主流程与滑块线程复用
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from functools import partial
from typing import Any
from urllib.parse import urlparse

import aiohttp
import requests
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.db.compat import db_manager
from common.db.retry import with_db_retry
from common.db.session import async_session_maker
from common.models.system_setting import SystemSetting
from common.models.user_setting import UserSetting
from common.models.xy_account import XYAccount


TOKEN_REMOTE_URL_SETTING_KEY = "token.remote_url"
TOKEN_REMOTE_SECRET_KEY_SETTING_KEY = "token.remote_secret_key"
REMOTE_TOKEN_TYPE = "xianyu_token"

# 连通性测试会故意传空 Cookie，远程接口若只抱怨 Cookie 长度，说明地址与秘钥均已通过校验
REMOTE_TOKEN_EMPTY_COOKIES_HINTS = (
    "cookies长度不足",
    "cookie长度不足",
    "cookies不能为空",
    "cookie不能为空",
)


def is_remote_token_empty_cookies_message(message: str) -> bool:
    """判断远程接口返回是否仅为「Cookie 为空/长度不足」这类参数校验失败。

    连通性测试不传真实 Cookie，远程接口回复这类信息时表示请求已到达且秘钥有效，
    可视为连通性测试通过。

    Args:
        message: 远程接口返回的 message 文案。
    Returns:
        属于空 Cookie 参数校验失败返回 True，否则返回 False。
    """
    normalized = str(message or "").replace(" ", "").replace("　", "").lower()
    if not normalized:
        return False
    # 只有 Cookie 参数校验失败才算连通；混合鉴权、余额或限流错误必须如实返回失败。
    other_error_hints = (
        "秘钥", "密钥", "鉴权", "认证", "授权", "权限", "余额", "配额", "额度", "限流", "频率",
        "api-key", "api_key", "unauthorized", "forbidden", "invalid", "quota", "rate limit",
    )
    if any(hint.replace(" ", "") in normalized for hint in other_error_hints):
        return False
    return any(hint in normalized for hint in REMOTE_TOKEN_EMPTY_COOKIES_HINTS)


@dataclass(frozen=True, slots=True)
class RemoteTokenSettings:
    """本次远程 Token 请求的配置及来源，重试时沿用同一份配置。"""

    url: str
    secret_key: str
    source: str = "系统设置"
    owner_id: int | None = None


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

    try:
        parsed = urlparse(clean_url)
        valid_url = (
            parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            and not any(char.isspace() for char in parsed.hostname)
            and not any(ord(char) < 32 or ord(char) == 127 for char in clean_url)
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        return "远程URL格式无效，请填写以 http:// 或 https:// 开头的完整地址"
    if any(ord(char) < 32 or ord(char) == 127 for char in clean_secret_key):
        return "秘钥不能包含换行或控制字符"
    return None


async def _query_remote_token_settings(
    account_id: str,
    session_maker: async_sessionmaker[AsyncSession],
) -> RemoteTokenSettings:
    """在同一会话中按账号选取个人或系统配置，供同步和异步入口复用。

    Args:
        account_id: 闲鱼账号标识；空值表示只读取系统配置。
        session_maker: 统一数据库层提供的会话工厂。
    Returns:
        个人配置任一项非空时选取整组个人配置，不与系统配置混用。
    Raises:
        ValueError: 指定账号不存在，无法确定配置所属用户。
    """
    keys = (TOKEN_REMOTE_URL_SETTING_KEY, TOKEN_REMOTE_SECRET_KEY_SETTING_KEY)
    owner_id = None
    async with session_maker() as session:
        if account_id:
            owner_id = (await session.execute(
                select(XYAccount.owner_id).where(XYAccount.account_id == account_id)
            )).scalar_one_or_none()
            if owner_id is None:
                raise ValueError(f"闲鱼账号{account_id}不存在，无法读取所属用户的Token远程配置")
            result = await session.execute(
                select(UserSetting.key, UserSetting.value).where(
                    UserSetting.user_id == owner_id,
                    UserSetting.key.in_(keys),
                ).order_by(UserSetting.id)
            )
            personal = {key: str(value or "").strip() for key, value in result.all()}
            personal_url = personal.get(TOKEN_REMOTE_URL_SETTING_KEY, "")
            personal_secret = personal.get(TOKEN_REMOTE_SECRET_KEY_SETTING_KEY, "")
            # 个人配置不完整也不得借用系统秘钥或回退；由请求前的校验返回具体错误。
            if personal_url or personal_secret:
                return RemoteTokenSettings(
                    url=personal_url, secret_key=personal_secret,
                    source="个人设置", owner_id=owner_id,
                )
        result = await session.execute(
            select(SystemSetting.key, SystemSetting.value).where(SystemSetting.key.in_(keys))
        )
        settings = {key: value for key, value in result.all()}
    return RemoteTokenSettings(
        url=str(settings.get(TOKEN_REMOTE_URL_SETTING_KEY) or "").strip(),
        secret_key=str(
            settings.get(TOKEN_REMOTE_SECRET_KEY_SETTING_KEY) or ""
        ).strip(),
        owner_id=owner_id,
    )


@with_db_retry(max_retries=2, initial_delay=0.5)
async def load_remote_token_settings(account_id: str = "") -> RemoteTokenSettings:
    """异步选择账号所属用户配置，未配置时读取系统配置。

    Args:
        account_id: 闲鱼账号标识；空值保留仅读取系统设置的兼容行为。
    Returns:
        本次请求配置；查询失败直接抛出，不视为用户未配置。
    """
    return await _query_remote_token_settings(str(account_id or "").strip(), async_session_maker)


def load_remote_token_settings_sync(account_id: str = "") -> RemoteTokenSettings:
    """同步复用同一配置查询和数据库兼容层的重试，不创建额外连接池。

    Args:
        account_id: 闲鱼账号标识；空值表示只读取系统设置。
    Returns:
        选定配置；兼容层读取失败时抛出异常，禁止误用系统配置。
    """
    settings = db_manager._run_async(
        partial(_query_remote_token_settings, str(account_id or "").strip())
    )
    if settings is None:
        raise RuntimeError("远程Token接口配置读取失败，已停止本次请求")
    return settings


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


def _log_remote_token_failure(
    url: str,
    secret_key: str,
    cookies: str,
    *,
    status_code: int = 0,
    response_headers: Any = None,
    response_body: Any = None,
    error: BaseException | None = None,
) -> None:
    """完整记录失败请求与响应；同步、异步及测试入口共享同一日志格式。"""
    logger.opt(exception=error).error(
        "远程Token请求失败：method=POST url={} query={} request_headers={} request_body={} "
        "status_code={} response_headers={} response_body={} exception={}",
        str(url).strip(), urlparse(str(url).strip()).query,
        {"X-API-Key": str(secret_key).strip()}, _build_remote_token_payload(cookies),
        status_code, response_headers, response_body,
        f"{type(error).__name__}: {error}" if error else "",
    )


def _parse_remote_token_response(
    response_json: Any,
    status_code: int,
    duration_seconds: float,
) -> RemoteTokenResult:
    """校验 HTTP 状态及 JSON 字段类型，避免异常响应被误当成有效 Token。"""
    def failure(message: str) -> RemoteTokenResult:
        """保留本次原始响应，返回明确的业务失败。"""
        return RemoteTokenResult(
            success=False, message=message,
            response_json=response_json,
            status_code=status_code,
            duration_seconds=duration_seconds,
        )

    if not 200 <= status_code < 300:
        detail = response_json.get("message") if isinstance(response_json, dict) else ""
        return failure(f"远程接口HTTP状态异常（{status_code}）：{detail or '请求失败'}")
    if not isinstance(response_json, dict):
        return failure("远程接口返回格式无效，响应不是JSON对象")

    message = str(response_json.get("message") or "")
    if response_json.get("success") is not True:
        if response_json.get("success") is not False:
            return failure("远程接口返回格式无效，success必须为布尔值")
        return failure(message or "远程接口返回失败")

    data = response_json.get("data")
    if not isinstance(data, dict):
        return failure("远程接口返回成功但缺少data对象")

    token = data.get("token")
    device_id = data.get("device_id")
    api_mode = str(data.get("api_mode") or "").strip()
    if not isinstance(token, str) or not token.strip():
        return failure("远程接口返回成功但token不是非空字符串")
    if not isinstance(device_id, str) or not device_id.strip():
        return failure("远程接口返回成功但device_id不是非空字符串")
    # api_mode 为远程接口可选返回字段，缺失时不再校验，保持空字符串由下游兜底展示

    return RemoteTokenResult(
        success=True,
        message=message or "远程接口取Token成功",
        response_json=response_json,
        status_code=status_code,
        duration_seconds=duration_seconds,
        token=token.strip(),
        device_id=device_id.strip(),
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
    status_code, response_headers, response_body = 0, None, None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                str(url).strip(),
                json=_build_remote_token_payload(cookies),
                headers={"X-API-Key": str(secret_key).strip()},
                timeout=aiohttp.ClientTimeout(total=timeout_seconds),
            ) as response:
                status_code, response_headers = response.status, list(response.headers.items())
                try:
                    response_body = await response.json(content_type=None)
                except Exception:
                    response_body = await response.text()
                    raise
                result = _parse_remote_token_response(
                    response_body, status_code, time.time() - started_at,
                )
                if not result.success:
                    _log_remote_token_failure(
                        url, secret_key, cookies, status_code=status_code,
                        response_headers=response_headers, response_body=response_body,
                    )
                return result
    except Exception as exc:
        _log_remote_token_failure(
            url, secret_key, cookies, status_code=status_code,
            response_headers=response_headers, response_body=response_body, error=exc,
        )
        raise


async def request_remote_xianyu_token_from_settings(
    *,
    cookies: str = "",
    timeout_seconds: int = 30,
    account_id: str = "",
    settings: RemoteTokenSettings | None = None,
) -> RemoteTokenResult:
    """异步调用账号选定的远程配置，任何请求失败均不回退系统配置。

    Args:
        cookies: 账号完整 Cookie。
        timeout_seconds: 单次请求超时秒数。
        account_id: 用于读取所属用户配置的账号标识。
        settings: 调用方已选定的配置，重试时原样复用。
    Returns:
        选定远程接口的真实结果，异常直接交给调用方处理。
    """
    settings = settings if settings is not None else await load_remote_token_settings(account_id)
    logger.info(
        "远程Token配置来源：account_id={} owner_id={} source={}",
        account_id, settings.owner_id, settings.source,
    )
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
    try:
        response = requests.post(
            str(url).strip(),
            json=_build_remote_token_payload(cookies),
            headers={"X-API-Key": str(secret_key).strip()},
            timeout=timeout_seconds,
        )
    except Exception as exc:
        _log_remote_token_failure(url, secret_key, cookies, error=exc)
        raise
    try:
        response_json = response.json()
    except Exception as exc:
        _log_remote_token_failure(
            url, secret_key, cookies, status_code=response.status_code,
            response_headers=list(response.headers.items()), response_body=response.text, error=exc,
        )
        raise
    result = _parse_remote_token_response(response_json, response.status_code, time.time() - started_at)
    if not result.success:
        _log_remote_token_failure(
            url, secret_key, cookies, status_code=response.status_code,
            response_headers=list(response.headers.items()), response_body=response_json,
        )
    return result


def request_remote_xianyu_token_from_settings_sync(
    *,
    cookies: str = "",
    timeout_seconds: float = 10,
    account_id: str = "",
    settings: RemoteTokenSettings | None = None,
) -> RemoteTokenResult:
    """同步调用账号选定的配置，用户接口失败时保留该结果，不回退系统配置。

    Args:
        cookies: 账号完整 Cookie。
        timeout_seconds: 请求超时秒数。
        account_id: 用于读取所属用户配置的账号标识。
        settings: 调用方已选定的配置，避免测试校验与请求之间再次选取。
    Returns:
        选定远程接口的真实结果，异常直接交给调用方处理。
    """
    settings = settings if settings is not None else load_remote_token_settings_sync(account_id)
    logger.info(
        "远程Token配置来源：account_id={} owner_id={} source={}",
        account_id, settings.owner_id, settings.source,
    )
    return request_remote_xianyu_token_sync(
        settings.url,
        settings.secret_key,
        cookies=cookies,
        timeout_seconds=timeout_seconds,
    )
