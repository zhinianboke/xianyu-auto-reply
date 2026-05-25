"""
COOKIES续期浏览器服务

功能：
1. 调用 WebSocket 服务内部接口执行 COOKIES 浏览器续期
2. 统一由 WebSocket 服务承担浏览器执行职责
3. 返回浏览器提取到的完整 Cookie 快照，供定时任务做增量更新
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from common.models.xy_account import XYAccount
from app.core.config import get_settings
from app.core.http_client import get_http_client


@dataclass(slots=True)
class CookiesRefreshBrowserResult:
    """浏览器续期执行结果。"""

    success: bool
    message: str
    cookies: list[dict[str, Any]]


class CookiesRefreshBrowserService:
    """COOKIES续期浏览器服务。"""

    async def refresh_account_cookies(self, account: XYAccount) -> CookiesRefreshBrowserResult:
        """执行单个账号的浏览器COOKIES续期。"""
        settings = get_settings()
        http_client = get_http_client()
        logger.info(f"【COOKIES续期】账号 {account.account_id} 开始调用 websocket COOKIES续期接口")
        try:
            response = await http_client.post(
                f"{settings.websocket_service_url}/internal/cookies/refresh",
                json={"account_id": account.account_id},
            )
        except Exception as exc:
            logger.error(f"【COOKIES续期】账号 {account.account_id} 调用 websocket COOKIES续期接口失败: {exc}")
            raise

        if not isinstance(response, dict):
            logger.error(f"【COOKIES续期】账号 {account.account_id} 调用 websocket COOKIES续期接口失败: 返回格式异常 {response}")
            return CookiesRefreshBrowserResult(
                success=False,
                message=f"COOKIES续期接口返回格式异常: {response}",
                cookies=[],
            )

        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        cookies = data.get("cookies") if isinstance(data.get("cookies"), list) else []
        success = bool(response.get("success", False))
        message = str(response.get("message") or "COOKIES续期接口未返回消息")
        if not success:
            logger.warning(f"【COOKIES续期】账号 {account.account_id} 调用 websocket COOKIES续期接口失败: {message}")
        return CookiesRefreshBrowserResult(
            success=success,
            message=message,
            cookies=cookies,
        )


cookies_refresh_browser_service = CookiesRefreshBrowserService()
