"""
协议登录远程接口客户端（阿里滑块获取 x5sec）。

功能：
1. 校验协议登录远程接口配置（URL、秘钥）
2. 按约定使用 X-API-Key 请求头调用远程接口，请求体 type=x5sec_ali
3. 提供连通性测试入口：验证远程URL可达且秘钥被接受
4. 提供求解入口：把淘宝滑块 punish 链接交给远程，取回 x5sec 等校验 Cookie
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
from loguru import logger

# 协议登录远程接口配置的系统设置键，与前端保持一致
PASSWORD_LOGIN_REMOTE_URL_SETTING_KEY = "password_login.remote_url"
PASSWORD_LOGIN_REMOTE_SECRET_KEY_SETTING_KEY = "password_login.remote_secret_key"
# 远程接口请求体的业务类型：阿里滑块获取 x5sec
REMOTE_X5SEC_TYPE = "x5sec_ali"

# 判定为「秘钥无效/鉴权失败」的远程返回文案关键片段
SECRET_KEY_INVALID_HINTS = (
    "秘钥无效",
    "秘钥错误",
    "缺少秘钥",
    "api-key",
    "api_key",
    "鉴权失败",
    "认证失败",
    "unauthorized",
    "forbidden",
)


@dataclass(frozen=True, slots=True)
class RemotePasswordLoginTestResult:
    """协议登录远程接口连通性测试结果。"""

    success: bool
    message: str
    status_code: int
    duration_seconds: float


def validate_remote_password_login_settings(url: str, secret_key: str) -> str | None:
    """校验协议登录远程接口配置。

    Args:
        url: 远程接口 URL。
        secret_key: 接口秘钥，会作为 X-API-Key 请求头发送。
    Returns:
        校验通过返回 None，否则返回中文错误信息。
    """
    clean_url = str(url or "").strip()
    clean_secret_key = str(secret_key or "").strip()
    if not clean_url:
        return "选择协议登录时必须填写远程URL"
    if not clean_secret_key:
        return "选择协议登录时必须填写秘钥"

    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "远程URL格式无效，请填写以 http:// 或 https:// 开头的完整地址"
    return None


def _is_secret_key_invalid_message(message: str) -> bool:
    """判断远程返回文案是否表示秘钥无效/鉴权失败。"""
    normalized = str(message or "").replace(" ", "").lower()
    if not normalized:
        return False
    return any(hint in normalized for hint in SECRET_KEY_INVALID_HINTS)


async def test_remote_password_login_interface(
    url: str,
    secret_key: str,
    *,
    timeout_seconds: int = 15,
) -> RemotePasswordLoginTestResult:
    """测试协议登录远程接口连通性与秘钥有效性。

    连通性测试只传空 data.url，远程若因缺少滑块页面链接而返回失败，说明地址与秘钥均已通过；
    仅当返回鉴权/秘钥相关错误或 HTTP 异常时才判定失败。

    Args:
        url: 远程接口 URL。
        secret_key: 接口秘钥，会作为 X-API-Key 请求头发送。
        timeout_seconds: 请求总超时时间。
    Returns:
        连通性测试结果。
    """
    error_message = validate_remote_password_login_settings(url, secret_key)
    if error_message:
        return RemotePasswordLoginTestResult(
            success=False,
            message=error_message,
            status_code=0,
            duration_seconds=0,
        )

    payload: dict[str, Any] = {"type": REMOTE_X5SEC_TYPE, "data": {"url": ""}}
    started_at = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                str(url).strip(),
                json=payload,
                headers={"X-API-Key": str(secret_key).strip()},
                timeout=aiohttp.ClientTimeout(total=timeout_seconds),
            ) as response:
                status_code = response.status
                try:
                    response_json = await response.json(content_type=None)
                except Exception:
                    response_json = None
                duration_seconds = time.time() - started_at
    except Exception as exc:
        return RemotePasswordLoginTestResult(
            success=False,
            message=f"无法连接远程接口：{type(exc).__name__}: {exc}",
            status_code=0,
            duration_seconds=time.time() - started_at,
        )

    # 鉴权失败的常见状态码：直接判定秘钥无效
    if status_code in (401, 403):
        return RemotePasswordLoginTestResult(
            success=False,
            message="连接成功，但秘钥无效",
            status_code=status_code,
            duration_seconds=duration_seconds,
        )

    if status_code != 200:
        return RemotePasswordLoginTestResult(
            success=False,
            message=f"远程接口返回异常（HTTP {status_code}），请检查远程URL是否正确",
            status_code=status_code,
            duration_seconds=duration_seconds,
        )

    remote_message = ""
    if isinstance(response_json, dict):
        remote_message = str(response_json.get("message") or "").strip()

    if _is_secret_key_invalid_message(remote_message):
        return RemotePasswordLoginTestResult(
            success=False,
            message=f"连接成功，但秘钥无效（远程：{remote_message}）",
            status_code=status_code,
            duration_seconds=duration_seconds,
        )

    return RemotePasswordLoginTestResult(
        success=True,
        message=f"远程接口连通性测试成功（远程返回：{remote_message or '正常'}）",
        status_code=status_code,
        duration_seconds=duration_seconds,
    )


# 求解成功时优先注入的登录滑块校验 Cookie，x5sec 为必需项，其余为上游附带校验值
_X5SEC_COOKIE_KEYS = ("x5sec", "bx-pp", "bx_et")


async def solve_remote_x5sec_login(
    url: str,
    secret_key: str,
    *,
    account_id: str,
    punish_url: str,
    timeout_seconds: int = 90,
) -> Tuple[str, Optional[Dict[str, str]], Optional[str]]:
    """调用协议登录远程接口（x5sec_ali）求解登录滑块。

    请求体 {"type":"x5sec_ali","data":{"url": punish_url}}，成功时远程返回
    data.x5sec（滑块校验 Cookie）及可选的 bx-pp、bx_et，供重发 login.do 携带。

    Args:
        url: 远程接口 URL。
        secret_key: 接口秘钥，作为 X-API-Key 请求头发送。
        account_id: 账号标识，仅用于日志。
        punish_url: login.do 返回的淘宝滑块 punish 完整链接。
        timeout_seconds: 请求总超时时间（远程需真实过滑块，给足时间）。
    Returns:
        (status, cookies, message)，status: 'ok'（cookies 含 x5sec）/ 'fail'。
    """
    error_message = validate_remote_password_login_settings(url, secret_key)
    if error_message:
        return "fail", None, error_message

    if not str(punish_url or "").strip():
        return "fail", None, "缺少滑块 punish 链接"

    payload: dict[str, Any] = {
        "type": REMOTE_X5SEC_TYPE,
        "data": {"url": str(punish_url).strip()},
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                str(url).strip(),
                json=payload,
                headers={"X-API-Key": str(secret_key).strip()},
                timeout=aiohttp.ClientTimeout(total=timeout_seconds),
            ) as response:
                status_code = response.status
                try:
                    data = await response.json(content_type=None)
                except Exception:
                    data = None
    except Exception as exc:
        logger.warning(
            f"【{account_id}】协议登录远程过滑块(x5sec_ali)调用失败: "
            f"{type(exc).__name__}: {exc}"
        )
        return "fail", None, f"远程接口调用失败: {type(exc).__name__}: {exc}"

    if status_code != 200:
        return "fail", None, f"远程接口返回异常（HTTP {status_code}）"

    if not isinstance(data, dict) or not data.get("success"):
        message = (
            str(data.get("message") or "").strip() if isinstance(data, dict) else ""
        )
        return "fail", None, message or "远程过滑块未通过"

    result = data.get("data") or {}
    if not isinstance(result, dict):
        return "fail", None, "远程接口返回成功但缺少data对象"

    x5sec = str(result.get("x5sec") or "").strip()
    if not x5sec:
        return "fail", None, "远程接口返回成功但缺少 x5sec"

    cookies: Dict[str, str] = {}
    for key in _X5SEC_COOKIE_KEYS:
        value = str(result.get(key) or "").strip()
        if value:
            cookies[key] = value
    return "ok", cookies, None
