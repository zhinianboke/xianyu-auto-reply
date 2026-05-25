"""
Cookie浏览器续期共通服务

功能：
1. 接口续期失败后，使用Playwright打开浏览器访问 https://www.goofish.com/im
2. 检测页面是否有[快速进入]按钮（登录iframe中的submit按钮）
3. 如果有[快速进入]按钮，点击后等待2秒获取cookies，视为浏览器续期成功
4. 如果没有[快速进入]按钮，视为浏览器续期失败，需要执行账号密码登录

本模块为纯工具服务，不依赖数据库、不依赖定时任务框架，
任何需要通过浏览器续期Cookie的场景都可以直接调用。
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from loguru import logger

from common.utils.xianyu_utils import trans_cookies
from common.utils.browser_utils import ensure_playwright_browser_path, get_chromium_executable_path

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False


# 浏览器续期目标URL
_TARGET_URL = "https://www.goofish.com/"
# 页面加载等待时间（秒）
_PAGE_LOAD_WAIT_SECONDS = 3
# 点击[快速进入]后等待时间（秒）
_AFTER_CLICK_WAIT_SECONDS = 2
# 浏览器操作超时（毫秒）
_BROWSER_TIMEOUT_MS = 30000


@dataclass(slots=True)
class CookieRenewBrowserResult:
    """浏览器续期结果。

    Attributes:
        success: 浏览器续期是否成功（找到[快速进入]按钮并成功获取cookies）
        has_quick_enter: 是否找到[快速进入]按钮
        new_cookies_str: 浏览器获取到的Cookie字符串（成功时有值）
        updated_cookie_names: 实际发生变化的Cookie字段名列表
        message: 结果描述信息
    """

    success: bool
    has_quick_enter: bool = False
    new_cookies_str: str = ""
    updated_cookie_names: list[str] = field(default_factory=list)
    message: str = ""


class CookieRenewBrowserService:
    """Cookie浏览器续期共通服务。

    使用方式：
        from common.services.cookie_renew_browser_service import cookie_renew_browser_service

        result = await cookie_renew_browser_service.renew(cookies_str, account_id)
        if result.success:
            # 浏览器续期成功，使用 result.new_cookies_str
            ...
        elif not result.has_quick_enter:
            # 没有[快速进入]按钮，需要执行账号密码登录
            ...
    """

    # 浏览器启动参数
    BROWSER_ARGS = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-web-security",
        "--disable-blink-features=AutomationControlled",
        "--disable-extensions",
        "--disable-plugins",
        "--disable-notifications",
        "--disable-popup-blocking",
        "--lang=zh-CN",
    ]

    # Cookie注入的域名列表
    COOKIE_DOMAINS = [".goofish.com", ".taobao.com", ".alipay.com"]

    async def renew(
        self,
        cookies_str: str,
        account_id: str = "",
    ) -> CookieRenewBrowserResult:
        """执行浏览器续期。

        使用cookies打开浏览器访问闲鱼IM页面，检测是否有[快速进入]按钮：
        - 有按钮：点击后获取cookies，视为浏览器续期成功
        - 无按钮：视为浏览器续期失败，需要执行账号密码登录

        Args:
            cookies_str: 当前完整的Cookie字符串
            account_id: 账号ID（仅用于日志标识，可为空）

        Returns:
            CookieRenewBrowserResult: 浏览器续期结果
        """
        log_prefix = (
            f"【Cookie浏览器续期】账号 {account_id}"
            if account_id
            else "【Cookie浏览器续期】"
        )

        if not PLAYWRIGHT_AVAILABLE:
            return CookieRenewBrowserResult(
                success=False,
                has_quick_enter=False,
                message="Playwright未安装，无法执行浏览器续期",
            )

        if not cookies_str or not cookies_str.strip():
            return CookieRenewBrowserResult(
                success=False,
                has_quick_enter=False,
                message="Cookie为空，无法执行浏览器续期",
            )

        logger.info(f"{log_prefix} 开始执行浏览器续期...")

        # 在线程中执行同步Playwright操作
        result = await asyncio.to_thread(
            self._sync_browser_renew, cookies_str, account_id, log_prefix
        )

        # 如果浏览器获取到了新cookies，计算更新字段
        if result.success and result.new_cookies_str:
            try:
                original_cookies = trans_cookies(cookies_str) if cookies_str else {}
                new_cookies = (
                    trans_cookies(result.new_cookies_str)
                    if result.new_cookies_str
                    else {}
                )
                updated_names = [
                    name
                    for name, value in new_cookies.items()
                    if original_cookies.get(name) != value
                ]
                result.updated_cookie_names = updated_names
            except Exception:
                pass

        return result

    def _sync_browser_renew(
        self,
        cookies_str: str,
        account_id: str,
        log_prefix: str,
    ) -> CookieRenewBrowserResult:
        """在线程中同步执行浏览器续期操作。"""
        playwright = None
        browser = None
        context = None
        page = None

        try:
            # Windows兼容性处理
            if sys.platform == "win32":
                try:
                    asyncio.set_event_loop_policy(
                        asyncio.WindowsProactorEventLoopPolicy()
                    )
                except Exception:
                    pass

            # 设置浏览器路径
            ensure_playwright_browser_path()

            logger.info(f"{log_prefix} 启动Playwright浏览器...")
            playwright = sync_playwright().start()

            # 构建启动参数
            launch_kwargs: dict[str, Any] = {
                "headless": False,
                "args": self.BROWSER_ARGS,
            }
            # Docker环境下强制无头模式（容器内无显示器）
            if os.environ.get("BROWSER_HEADLESS", "").lower() == "true":
                launch_kwargs["headless"] = True

            chromium_path = get_chromium_executable_path()
            if chromium_path:
                launch_kwargs["executable_path"] = chromium_path

            browser = playwright.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36"
                ),
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )

            # 注入反检测脚本
            page = context.new_page()
            page.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en']
                });
                window.chrome = { runtime: {} };
                """
            )

            # 注入cookies到浏览器
            cookie_payloads = self._build_cookie_payloads(cookies_str)
            if cookie_payloads:
                context.add_cookies(cookie_payloads)
                logger.info(
                    f"{log_prefix} 已注入 {len(cookie_payloads)} 个Cookie"
                )

            # 访问目标页面
            logger.info(f"{log_prefix} 访问页面: {_TARGET_URL}")
            page.goto(
                _TARGET_URL,
                wait_until="domcontentloaded",
                timeout=_BROWSER_TIMEOUT_MS,
            )

            # 等待页面加载
            logger.info(f"{log_prefix} 等待页面加载（{_PAGE_LOAD_WAIT_SECONDS}秒）...")
            time.sleep(_PAGE_LOAD_WAIT_SECONDS)

            # 查找[快速进入]按钮
            quick_enter_found = self._find_and_click_quick_enter(
                page, log_prefix
            )

            if quick_enter_found:
                # 点击成功，等待2秒让页面完成跳转和cookie更新
                logger.info(
                    f"{log_prefix} 已点击[快速进入]，等待{_AFTER_CLICK_WAIT_SECONDS}秒..."
                )
                time.sleep(_AFTER_CLICK_WAIT_SECONDS)
            else:
                # 没有[快速进入]按钮，检查是否已经处于登录状态（页面直接进入了IM）
                logger.info(f"{log_prefix} 未找到[快速进入]按钮，检查是否已登录...")
                if self._check_already_logged_in(page, log_prefix):
                    logger.info(f"{log_prefix} 检测到已登录状态，直接获取Cookie")
                else:
                    logger.warning(f"{log_prefix} 未找到[快速进入]按钮且未检测到登录状态，浏览器续期失败")
                    return CookieRenewBrowserResult(
                        success=False,
                        has_quick_enter=False,
                        message="未找到[快速进入]按钮且未检测到登录状态，需要账号密码登录",
                    )

            # 获取浏览器中的所有cookies
            browser_cookies = context.cookies()
            if not browser_cookies:
                logger.warning(f"{log_prefix} 点击后未获取到浏览器Cookie")
                return CookieRenewBrowserResult(
                    success=False,
                    has_quick_enter=True,
                    message="点击[快速进入]后未获取到浏览器Cookie",
                )

            # 将浏览器cookies转换为字符串格式
            # 注意：浏览器获取到的Cookie需要合并到原始Cookie中，而不是完全替换
            # 因为浏览器可能只拿到部分域的Cookie，缺少 _m_h5_tk 等关键字段
            browser_cookies_dict: Dict[str, str] = {}
            for cookie in browser_cookies:
                name = cookie.get("name", "")
                value = cookie.get("value", "")
                if name and value:
                    browser_cookies_dict[name] = value

            if not browser_cookies_dict:
                logger.warning(f"{log_prefix} 浏览器Cookie解析为空")
                return CookieRenewBrowserResult(
                    success=False,
                    has_quick_enter=True,
                    message="点击[快速进入]后Cookie解析为空",
                )

            # 将浏览器Cookie合并到原始Cookie中（浏览器的值覆盖原始值）
            try:
                original_dict = trans_cookies(cookies_str) if cookies_str else {}
            except Exception:
                original_dict = {}

            merged_dict: Dict[str, str] = dict(original_dict)
            merged_dict.update(browser_cookies_dict)

            new_cookies_str = "; ".join(
                f"{name}={value}" for name, value in merged_dict.items()
            )

            logger.info(
                f"{log_prefix} 浏览器续期成功，获取到 {len(browser_cookies_dict)} 个Cookie字段，"
                f"合并后共 {len(merged_dict)} 个字段"
            )
            return CookieRenewBrowserResult(
                success=True,
                has_quick_enter=True,
                new_cookies_str=new_cookies_str,
                message=f"浏览器续期成功，获取到 {len(browser_cookies_dict)} 个Cookie字段，合并后共 {len(merged_dict)} 个",
            )

        except Exception as exc:
            logger.error(f"{log_prefix} 浏览器续期异常: {exc}")
            return CookieRenewBrowserResult(
                success=False,
                has_quick_enter=False,
                message=f"浏览器续期异常: {exc}",
            )
        finally:
            # 清理浏览器资源
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

    def _check_already_logged_in(self, page, log_prefix: str) -> bool:
        """检查页面是否已经处于登录状态。

        判断依据：
        1. 右上角有用户昵称/头像（说明已登录，可能触发了滑块验证）
        2. 页面有消息列表（IM页面核心元素）
        3. 页面有滑块验证弹窗（说明已登录但触发风控）

        Args:
            page: Playwright页面对象
            log_prefix: 日志前缀

        Returns:
            是否已登录
        """
        # 检测已登录的选择器列表
        logged_in_selectors = [
            # 右上角用户昵称区域
            'div.nick',
            '.header-right .nick',
            # 消息列表（IM页面核心元素）
            '.rc-virtual-list-holder-inner',
            # 头像图片（alicdn头像）
            'img[src*="img.alicdn.com"][class*="avatar"]',
            'img[src*="img.alicdn.com"][style*="border-radius"]',
            # header中的用户头像（从截图看是圆形头像）
            '.header-container img[src*="img.alicdn.com"]',
            # 滑块验证弹窗（说明已登录但触发了风控，也算登录成功）
            '#nc_1_n1z',
            '.nc-container',
            '.nc_scale',
            'div:has-text("请拖动下方滑块完成验证")',
            'div:has-text("请按住滑块")',
        ]

        for selector in logged_in_selectors:
            try:
                element = page.query_selector(selector)
                if element and element.is_visible():
                    logger.info(
                        f"{log_prefix} 检测到已登录元素: {selector}"
                    )
                    return True
            except Exception:
                continue

        # 兜底：检查页面文本中是否有"消息"字样（IM页面标题）
        try:
            body_text = page.text_content("body") or ""
            if "消息" in body_text and ("订单" in body_text or "发闲置" in body_text):
                logger.info(f"{log_prefix} 通过页面文本检测到已登录状态")
                return True
        except Exception:
            pass

        return False

    def _find_and_click_quick_enter(self, page, log_prefix: str) -> bool:
        """查找并点击[快速进入]按钮。

        按钮位于登录iframe中，结构为：
        <button type="submit" tabindex="1" class="...">快速进入</button>

        Args:
            page: Playwright页面对象
            log_prefix: 日志前缀

        Returns:
            是否找到并成功点击了[快速进入]按钮
        """
        # 策略1：在主页面直接查找[快速进入]按钮
        if self._try_click_quick_enter_in_frame(page, log_prefix, "主页面"):
            return True

        # 策略2：在所有iframe中查找[快速进入]按钮
        try:
            iframes = page.query_selector_all("iframe")
            logger.info(f"{log_prefix} 找到 {len(iframes)} 个iframe，逐一检查...")

            for idx, iframe in enumerate(iframes):
                try:
                    frame = iframe.content_frame()
                    if not frame:
                        continue

                    # 等待iframe内容加载
                    try:
                        frame.wait_for_load_state(
                            "domcontentloaded", timeout=5000
                        )
                    except Exception:
                        pass

                    if self._try_click_quick_enter_in_frame(
                        frame, log_prefix, f"iframe[{idx}]"
                    ):
                        return True
                except Exception as exc:
                    logger.info(
                        f"{log_prefix} 检查iframe[{idx}]时出错: {exc}"
                    )
                    continue
        except Exception as exc:
            logger.warning(f"{log_prefix} 查找iframe时出错: {exc}")

        return False

    def _try_click_quick_enter_in_frame(
        self, frame, log_prefix: str, frame_name: str
    ) -> bool:
        """在指定frame中尝试查找并点击[快速进入]按钮。

        Args:
            frame: 页面或frame对象
            log_prefix: 日志前缀
            frame_name: frame名称（用于日志）

        Returns:
            是否成功点击
        """
        # 要匹配的按钮文本
        target_text = "快速进入"

        # 选择器列表：按优先级排列（Playwright :has-text 使用引号包裹文本）
        selectors = [
            # 精确匹配：包含"快速进入"文本的button
            f'button:has-text("{target_text}")',
            # submit类型的button
            f'button[type="submit"]:has-text("{target_text}")',
            # class中包含fm-button的按钮（从截图中看到的class）
            f'.fm-button:has-text("{target_text}")',
            f'.fn-button:has-text("{target_text}")',
        ]

        for selector in selectors:
            try:
                element = frame.query_selector(selector)
                if element and element.is_visible():
                    logger.info(
                        f"{log_prefix} ✓ 在{frame_name}找到[快速进入]按钮: {selector}"
                    )
                    element.click()
                    logger.info(f"{log_prefix} ✓ [快速进入]按钮已点击")
                    return True
            except Exception:
                continue

        # 兜底策略：通过文本内容匹配所有button
        try:
            buttons = frame.query_selector_all("button")
            for btn in buttons:
                try:
                    text = btn.text_content() or ""
                    if target_text in text.strip() and btn.is_visible():
                        logger.info(
                            f"{log_prefix} ✓ 在{frame_name}通过文本匹配找到[快速进入]按钮"
                        )
                        btn.click()
                        logger.info(f"{log_prefix} ✓ [快速进入]按钮已点击")
                        return True
                except Exception:
                    continue
        except Exception:
            pass

        return False

    def _build_cookie_payloads(
        self, cookies_str: str
    ) -> list[dict[str, Any]]:
        """将Cookie字符串转换为Playwright可识别的Cookie列表。

        Args:
            cookies_str: Cookie字符串

        Returns:
            Playwright cookie payload列表
        """
        try:
            cookie_dict = trans_cookies(cookies_str) if cookies_str else {}
        except Exception:
            cookie_dict = {}

        payloads: list[dict[str, Any]] = []
        for name, value in cookie_dict.items():
            if not name or not value:
                continue
            for domain in self.COOKIE_DOMAINS:
                payloads.append(
                    {
                        "name": name,
                        "value": value,
                        "domain": domain,
                        "path": "/",
                    }
                )
        return payloads


# 全局单例
cookie_renew_browser_service = CookieRenewBrowserService()
