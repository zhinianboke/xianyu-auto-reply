"""
Token 续期滑块处理模块。

功能：
1. 调用 WebSocket 内部滑块接口
2. 合并滑块返回的 Cookie
3. 读取 WebSocket 端已写入 Token 缓存的结果
4. 返回可直接写入续期日志的具体失败原因
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loguru import logger

from common.services.account_cookie_service import merge_account_cookie_fields
from common.services.captcha.token_response import extract_token_captcha_url
from common.services.captcha.websocket_solver import solve_captcha_via_websocket


@dataclass(frozen=True, slots=True)
class CaptchaRenewalResult:
    """滑块续期阶段结果。"""

    cookies_str: str | None = None
    failure_message: str | None = None
    cache_saved: bool = False
    renew_expire_at: datetime | None = None
    cache_message: str | None = None


def _parse_datetime(value: Any) -> datetime | None:
    """解析 WebSocket 端返回的到期时间。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


async def solve_token_captcha_and_merge_cookies(
    *,
    task_name: str,
    websocket_service_url: str,
    account_id: str,
    account_row_id: int,
    cache_id: int,
    token_user_id: str,
    device_id: str,
    cookies_str: str,
    response_json: Any,
) -> CaptchaRenewalResult:
    """调用过滑块并返回后续续期所需结果。

    Args:
        task_name: 调度任务名称，仅用于日志。
        websocket_service_url: WebSocket 服务地址。
        account_id: 闲鱼账号 ID。
        account_row_id: ``xy_accounts.id``。
        cache_id: ``xy_token_cache.id``。
        token_user_id: Token 缓存用户 ID。
        device_id: 当前 Token 缓存 Device ID。
        cookies_str: 当前账号 Cookie。
        response_json: Token 接口返回内容。
    Returns:
        成功时返回新 Cookie 或已写缓存状态；失败时返回具体中文原因。
    """
    verification_url = extract_token_captcha_url(response_json)
    if not verification_url:
        reason = "Token触发风控但未返回滑块链接"
        logger.error(f"【{task_name}】【{account_id}】{reason}")
        return CaptchaRenewalResult(failure_message=reason)

    result = await solve_captcha_via_websocket(
        websocket_service_url,
        account_id=account_id,
        account_row_id=account_row_id,
        token_cache_id=cache_id,
        token_user_id=token_user_id,
        url=verification_url,
        cookies=cookies_str,
        device_id=device_id,
    )
    if not result.get("success"):
        result_data = result.get("data")
        detail = str(result.get("message") or "未知错误")
        if isinstance(result_data, dict) and result_data.get("engine"):
            detail = f"{detail}（引擎={result_data.get('engine')}）"
        if result.get("_request_status_unknown"):
            detail = (
                f"{detail}；请求状态未知，WebSocket端可能仍在继续处理，"
                "若最终成功会尝试自动写回Cookie和Token缓存"
            )
        reason = f"滑块处理失败：{detail}"
        logger.error(f"【{task_name}】【{account_id}】{reason}")
        return CaptchaRenewalResult(failure_message=reason)

    result_data = result.get("data")
    new_cookies = result_data.get("cookies") if isinstance(result_data, dict) else None
    cache_saved = bool(
        isinstance(result_data, dict) and result_data.get("token_cache_saved")
    )
    if cache_saved:
        logger.info(f"【{task_name}】【{account_id}】WebSocket端已写入续期Token缓存")
        return CaptchaRenewalResult(
            cookies_str=cookies_str,
            cache_saved=True,
            renew_expire_at=_parse_datetime(result_data.get("renew_expire_at")),
            cache_message=str(result_data.get("token_cache_message") or "")
            or "续期成功（WebSocket端写入Token缓存）",
        )

    token_already_available = bool(
        isinstance(result_data, dict) and result_data.get("token_already_available")
    )
    if token_already_available:
        if isinstance(new_cookies, dict) and new_cookies:
            merged_cookies_str = await merge_account_cookie_fields(
                account_row_id,
                account_id,
                new_cookies,
            )
            if not merged_cookies_str:
                reason = "风控解除后的Cookie合并写回失败"
                logger.error(f"【{task_name}】【{account_id}】{reason}")
                return CaptchaRenewalResult(failure_message=reason)
        else:
            merged_cookies_str = cookies_str
        logger.info(f"【{task_name}】【{account_id}】重取验证链接时Token已可用")
        return CaptchaRenewalResult(cookies_str=merged_cookies_str)

    if not isinstance(new_cookies, dict) or not new_cookies:
        engine = result_data.get("engine") if isinstance(result_data, dict) else None
        reason = "滑块成功但未返回新Cookie"
        if engine:
            reason = f"{reason}（引擎={engine}）"
        logger.error(f"【{task_name}】【{account_id}】{reason}")
        return CaptchaRenewalResult(failure_message=reason)

    merged_cookies_str = await merge_account_cookie_fields(
        account_row_id,
        account_id,
        new_cookies,
    )
    if not merged_cookies_str:
        cookie_names = ",".join(str(name) for name in new_cookies.keys())[:200]
        reason = f"滑块Cookie合并写回失败（Cookie字段：{cookie_names or '无'}）"
        logger.error(f"【{task_name}】【{account_id}】{reason}")
        return CaptchaRenewalResult(failure_message=reason)

    logger.info(
        f"【{task_name}】【{account_id}】滑块成功，已合并 "
        f"{len(new_cookies)} 个Cookie，准备使用新Cookie重试Token"
    )
    return CaptchaRenewalResult(cookies_str=merged_cookies_str)
