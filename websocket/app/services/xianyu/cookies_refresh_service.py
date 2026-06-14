"""
COOKIES续期浏览器服务

功能：
1. 在 WebSocket 服务内执行账号 COOKIES 浏览器续期
2. 使用同步 Playwright 在线程中启动浏览器
3. 与现有浏览器槽位管理器共用并发控制
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Any

from loguru import logger

from common.utils.cookie_refresh import (
    build_playwright_cookie_payloads_from_snapshot,
    get_cookie_refresh_snapshot,
    normalize_browser_cookie_snapshot,
    normalize_cookie_string,
    parse_cookie_string,
)
from common.utils.browser_utils import ensure_playwright_browser_path, get_chromium_executable_path
from common.services.captcha.concurrency import run_browser_task

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False


@dataclass(slots=True)
class CookiesRefreshAccountContext:
    """COOKIES续期账号上下文。"""

    account_id: str
    cookie: str
    metadata_json: dict[str, Any] | None


@dataclass(slots=True)
class CookiesRefreshBrowserResult:
    """浏览器续期执行结果。"""

    success: bool
    message: str
    cookies: list[dict[str, Any]]


class CookiesRefreshService:
    """COOKIES续期浏览器服务。"""

    TARGET_URL = "https://www.goofish.com/"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    BROWSER_ARGS = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--lang=zh-CN",
    ]
    COOKIE_DOMAINS = [".goofish.com", ".taobao.com", ".alipay.com"]

    def _build_cookie_payloads(self, account: CookiesRefreshAccountContext) -> list[dict[str, Any]]:
        """构造 Playwright 可识别的 Cookie 列表。"""
        cookie_payloads = build_playwright_cookie_payloads_from_snapshot(
            get_cookie_refresh_snapshot(account.metadata_json)
        )
        if cookie_payloads:
            return cookie_payloads

        cookie_string = normalize_cookie_string(account.cookie or "")
        try:
            cookie_dict = parse_cookie_string(cookie_string)
        except Exception as exc:
            logger.warning(f"【COOKIES续期】Cookie解析失败: {exc}")
            cookie_dict = {}
        cookie_payloads: list[dict[str, Any]] = []
        for name, value in cookie_dict.items():
            for domain in self.COOKIE_DOMAINS:
                cookie_payloads.append(
                    {
                        "name": name,
                        "value": value,
                        "domain": domain,
                        "path": "/",
                    }
                )
        return cookie_payloads

    def _sync_refresh_account_cookies(
        self,
        account: CookiesRefreshAccountContext,
    ) -> CookiesRefreshBrowserResult:
        """在线程中同步执行浏览器 COOKIES 续期。"""
        if not PLAYWRIGHT_AVAILABLE or sync_playwright is None:
            return CookiesRefreshBrowserResult(
                success=False,
                message="Playwright 未安装，无法执行COOKIES续期",
                cookies=[],
            )

        playwright = None
        browser = None
        context = None
        page = None

        try:
            cookie_payloads = self._build_cookie_payloads(account)
            if not cookie_payloads:
                return CookiesRefreshBrowserResult(
                    success=False,
                    message="账号Cookie为空，且无可用Cookie快照，无法注入浏览器",
                    cookies=[],
                )

            if sys.platform == "win32":
                try:
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                except Exception as exc:
                    logger.warning(f"【COOKIES续期】设置事件循环策略失败: {exc}")

            ensure_playwright_browser_path()
            logger.info(f"【COOKIES续期】账号 {account.account_id} 启动Playwright...")
            playwright = sync_playwright().start()
            logger.info(f"【COOKIES续期】账号 {account.account_id} Playwright启动成功")

            launch_kwargs: dict[str, Any] = {
                "headless": True,
                "args": self.BROWSER_ARGS,
            }
            chromium_path = get_chromium_executable_path()
            if chromium_path:
                launch_kwargs["executable_path"] = chromium_path

            browser = playwright.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=self.USER_AGENT,
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            page = context.new_page()
            page.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
                window.chrome = { runtime: {} };
                """
            )

            context.add_cookies(cookie_payloads)
            page.goto(self.TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)

            for _ in range(3):
                page.reload(wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)

            modal_locator = page.locator(".ant-modal-body")
            modal_count = modal_locator.count()
            if modal_count > 0:
                modal_text = ""
                try:
                    modal_text = modal_locator.first.text_content() or ""
                except Exception:
                    modal_text = ""
                message = "页面存在 ant-modal-body，判定续期失败"
                if modal_text:
                    message = f"{message}: {modal_text[:120]}"
                return CookiesRefreshBrowserResult(success=False, message=message, cookies=[])

            refreshed_cookies = normalize_browser_cookie_snapshot(context.cookies())
            if not refreshed_cookies:
                return CookiesRefreshBrowserResult(
                    success=False,
                    message="页面刷新完成，但未获取到浏览器Cookie",
                    cookies=[],
                )

            return CookiesRefreshBrowserResult(
                success=True,
                message=f"页面校验通过，全量获取到 {len(refreshed_cookies)} 个浏览器Cookie",
                cookies=refreshed_cookies,
            )
        except Exception as exc:
            logger.error(f"【COOKIES续期】账号 {account.account_id} 浏览器续期失败: {exc}")
            return CookiesRefreshBrowserResult(
                success=False,
                message=f"浏览器续期异常: {exc}",
                cookies=[],
            )
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright:
                try:
                    playwright.stop()
                except Exception:
                    pass

    async def refresh_account_cookies(
        self,
        account_id: str,
        cookie: str,
        metadata_json: dict[str, Any] | None,
    ) -> CookiesRefreshBrowserResult:
        """执行单个账号的浏览器 COOKIES 续期。"""
        account = CookiesRefreshAccountContext(
            account_id=account_id,
            cookie=cookie,
            metadata_json=metadata_json,
        )
        # 浏览器续期为长阻塞任务，走专用线程池，避免占用 asyncio 默认线程池拖垮 aiohttp
        return await run_browser_task(self._sync_refresh_account_cookies, account)


cookies_refresh_service = CookiesRefreshService()
