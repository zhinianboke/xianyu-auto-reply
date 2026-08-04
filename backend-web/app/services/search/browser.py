"""
浏览器管理器

管理Playwright浏览器的初始化和关闭
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from typing import Any, Dict, List, Optional

from loguru import logger
from common.utils.browser_utils import ensure_playwright_browser_path, get_chromium_executable_path

# 修复Docker环境中的asyncio事件循环策略问题
if sys.platform.startswith('linux') or os.getenv('DOCKER_ENV'):
    try:
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    except Exception as e:
        logger.warning(f"设置事件循环策略失败: {e}")

if os.getenv('DOCKER_ENV'):
    try:
        if hasattr(asyncio, 'SelectorEventLoop'):
            loop = asyncio.SelectorEventLoop()
            asyncio.set_event_loop(loop)
    except Exception as e:
        logger.warning(f"设置SelectorEventLoop失败: {e}")

try:
    from playwright.async_api import async_playwright, Page, BrowserContext, Browser
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = Any
    BrowserContext = Any
    Browser = Any
    logger.warning("Playwright 未安装，将无法使用真实搜索功能")


class BrowserManager:
    """浏览器管理器"""

    # 浏览器启动参数
    DEFAULT_BROWSER_ARGS = [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--no-first-run',
        '--disable-extensions',
        '--disable-default-apps',
        '--no-default-browser-check',
        '--lang=zh-CN',
        '--accept-lang=zh-CN,zh,en-US,en'
    ]

    DOCKER_BROWSER_ARGS = [
        '--disable-gpu',
    ]

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        # A persistent Playwright profile can be opened by only one Chromium
        # process.  Each collector owns a short-lived profile so concurrent
        # research, monitoring and item-detail requests never fight for the
        # same ProcessSingleton lock.  Account cookies are injected for every
        # run, so this does not discard required login state.
        self._user_data_dir: Optional[str] = None

    @property
    def is_available(self) -> bool:
        """检查Playwright是否可用"""
        return PLAYWRIGHT_AVAILABLE

    async def init_browser(self, headless: bool = True) -> bool:
        """Initialize an isolated persistent context for this collector run."""
        if not PLAYWRIGHT_AVAILABLE:
            raise Exception("Playwright 未安装，无法使用真实搜索功能")

        if self.browser:
            return True

        # Docker环境下强制无头模式（容器内无显示器，有头模式会报错）
        if not headless and os.environ.get("BROWSER_HEADLESS", "").lower() == "true":
            logger.info("检测到BROWSER_HEADLESS=true，强制使用无头模式")
            headless = True

        try:
            ensure_playwright_browser_path()
            self.playwright = await async_playwright().start()

            # ``launch_persistent_context`` must not share a user-data-dir
            # between processes.  The previous fixed /tmp path caused one
            # task to fail whenever another task had Chromium open.
            self._user_data_dir = tempfile.mkdtemp(prefix="xianyu_browser_")
            logger.info("Created isolated browser profile for collector run")

            # 构建浏览器参数
            browser_args = self.DEFAULT_BROWSER_ARGS.copy()
            if os.getenv('DOCKER_ENV') == 'true':
                browser_args.extend(self.DOCKER_BROWSER_ARGS)

            logger.info("Starting browser with isolated collector profile...")
            chromium_path = get_chromium_executable_path()

            # 使用持久化上下文
            launch_kwargs = dict(
                headless=headless,
                args=browser_args,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720},
                locale='zh-CN',
            )
            if chromium_path:
                launch_kwargs["executable_path"] = chromium_path
            self.context = await self.playwright.chromium.launch_persistent_context(
                self._user_data_dir,
                **launch_kwargs,
            )

            self.browser = self.context.browser
            logger.info("Browser started with isolated persistent context")

            self.page = await self.context.new_page()
            logger.info("浏览器初始化完成")

            return True

        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            await self.close_browser()
            raise

    async def close_browser(self):
        """Close browser resources and remove the collector-owned profile."""
        page, context, playwright, profile_dir = (
            self.page,
            self.context,
            self.playwright,
            self._user_data_dir,
        )
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        self._user_data_dir = None

        for closer in (
            (page, "page"),
            (context, "context"),
            (playwright, "playwright"),
        ):
            resource, name = closer
            if not resource:
                continue
            try:
                if name == "playwright":
                    await resource.stop()
                else:
                    await resource.close()
            except Exception as exc:
                logger.warning(f"Failed to close browser {name}: {type(exc).__name__}")

        if profile_dir:
            try:
                await asyncio.to_thread(shutil.rmtree, profile_dir, ignore_errors=True)
            except Exception as exc:
                logger.warning(f"Failed to remove browser profile: {type(exc).__name__}")
        logger.debug("Browser collector resources closed")

    async def set_cookies(self, cookie_value: str) -> bool:
        """设置浏览器cookies"""
        try:
            if not cookie_value or not self.context:
                return False

            cookies = []
            for cookie_pair in cookie_value.split(';'):
                cookie_pair = cookie_pair.strip()
                if '=' in cookie_pair:
                    name, value = cookie_pair.split('=', 1)
                    cookies.append({
                        'name': name.strip(),
                        'value': value.strip(),
                        'domain': '.goofish.com',
                        'path': '/'
                    })

            await self.context.add_cookies(cookies)
            logger.info(f"成功设置 {len(cookies)} 个cookies到浏览器")
            return True

        except Exception as e:
            logger.error(f"设置浏览器cookies失败: {str(e)}")
            return False

    async def navigate_to(self, url: str, timeout: int = 30000) -> bool:
        """导航到指定URL"""
        try:
            if not self.page:
                return False

            await self.page.goto(url, timeout=timeout)
            return True

        except Exception as e:
            logger.error(f"导航失败: {e}")
            return False

    async def wait_for_network_idle(self, timeout: int = 15000):
        """等待网络空闲"""
        if self.page:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)

    async def fill_input(self, selector: str, value: str) -> bool:
        """填充输入框"""
        try:
            if not self.page:
                return False

            await self.page.fill(selector, value)
            return True

        except Exception as e:
            logger.error(f"填充输入框失败: {e}")
            return False

    async def click(self, selector: str) -> bool:
        """点击元素"""
        try:
            if not self.page:
                return False

            await self.page.click(selector)
            return True

        except Exception as e:
            logger.error(f"点击元素失败: {e}")
            return False

    async def press_key(self, key: str):
        """按下键盘按键"""
        if self.page:
            await self.page.keyboard.press(key)

    def on_response(self, callback):
        """注册响应监听器"""
        if self.page:
            self.page.on("response", callback)
