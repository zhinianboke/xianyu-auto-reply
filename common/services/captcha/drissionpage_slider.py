"""
DrissionPage 滑块验证兜底引擎

作为 Playwright 主引擎失败后的第二套滑块破解引擎。通过 DrissionPage 控制
Chromium（复用 Playwright 安装的同一 chromium 二进制）执行拟人化滑动。

设计要点（见 .kiro/specs/captcha-drissionpage-fallback/design.md）：
- 复用 Playwright 的本地化目录 browser_data/user_{id}（方案 A），延续缓存与已过滑块状态；
- 复用并发槽位与账号级互斥锁，启动前清理孤儿 Singleton 锁，避免 PROFILE_IN_USE；
- 滑动前注入数据库最新 cookie，保证使用最新 cookie；
- 返回契约与 run_slider_verification 一致：(是否成功, cookies 字典 | None)。

移植并精简自参照项目 utils/refresh_util.py 的 DrissionHandler。
"""
from __future__ import annotations

import os
import random
import time
from typing import Any, Dict, Optional, Tuple

from loguru import logger

from common.services.captcha.concurrency import concurrency_manager, account_browser_lock_manager
from common.services.captcha.drissionpage_tracks import generate_tracks
from common.services.captcha.drissionpage_motion import calculate_slide_distance, execute_tracks
from common.utils.browser_utils import ensure_playwright_browser_path, get_chromium_executable_path
from common.utils.xianyu_utils import trans_cookies

try:
    from DrissionPage import Chromium, ChromiumOptions
    DRISSIONPAGE_AVAILABLE = True
except ImportError:
    DRISSIONPAGE_AVAILABLE = False
    Chromium = Any
    ChromiumOptions = Any
    logger.warning("DrissionPage 未安装，滑块兜底引擎不可用（pip install DrissionPage）")


class DrissionPageSliderService:
    """DrissionPage 滑块验证兜底引擎"""

    # 滑块按钮选择器
    SLIDER_SELECTOR = "#nc_1_n1z"
    SLIDER_LOADED_SELECTOR = "x://span[contains(@id,'nc_1_n1z')]"
    # 验证拦截后的页面标题
    BLOCKED_TITLE = "验证码拦截"

    def __init__(
        self,
        user_id: str = "default",
        headless: bool = True,
        browser_timeout: int = 25,
        user_data_dir: Optional[str] = None,
    ):
        """初始化兜底引擎并启动浏览器。

        Args:
            user_id: 用户/账号 ID
            headless: 是否无头（Docker 必须 True）
            browser_timeout: 单次验证超时（秒）
            user_data_dir: 持久化用户数据目录；默认复用 Playwright 的 browser_data/user_{id}
        """
        if not DRISSIONPAGE_AVAILABLE:
            raise ImportError("DrissionPage 未安装，请运行: pip install DrissionPage")

        self.user_id = user_id
        self.browser_timeout = browser_timeout
        self.max_retries = 3
        self.slide_attempt = 0
        self.cookies: Dict[str, str] = {}
        self.refresh_next = False

        # Docker 环境强制无头
        if not headless and os.environ.get("BROWSER_HEADLESS", "").lower() == "true":
            logger.info(f"【{user_id}】检测到 BROWSER_HEADLESS=true，强制无头模式")
            headless = True
        self.headless = headless

        self.pure_user_id = concurrency_manager._extract_pure_user_id(user_id)

        # 方案 A：复用 Playwright 引擎的同一本地化目录
        self.user_data_dir = user_data_dir or os.path.join(
            os.getcwd(), "browser_data", f"user_{self.pure_user_id}"
        )
        os.makedirs(self.user_data_dir, exist_ok=True)

        self.browser = None
        self.page = None
        self._slot_acquired = False
        self._account_lock_acquired = False

        # 获取全局并发槽位
        logger.info(f"【{self.pure_user_id}】DrissionPage 兜底：检查并发槽位...")
        if not concurrency_manager.wait_for_slot(self.user_id):
            stats = concurrency_manager.get_stats()
            raise RuntimeError(
                f"DrissionPage 兜底等待槽位超时，当前活跃: "
                f"{stats['active_count']}/{stats['max_concurrent']}"
            )
        self._slot_acquired = True

        # 获取账号级互斥锁（与 Playwright 引擎复用同一目录，必须串行独占）
        try:
            account_lock_timeout = float(getattr(concurrency_manager, "wait_timeout", 120) or 120)
        except Exception:
            account_lock_timeout = 120.0
        logger.info(
            f"【{self.pure_user_id}】DrissionPage 兜底：获取账号级互斥锁（超时 {account_lock_timeout:.0f} 秒）..."
        )
        if not account_browser_lock_manager.acquire(self.pure_user_id, timeout=account_lock_timeout):
            self._release_slot()
            raise RuntimeError(
                f"账号 {self.pure_user_id} 已被另一个浏览器实例占用，"
                f"等待 {account_lock_timeout:.0f} 秒未释放"
            )
        self._account_lock_acquired = True
        logger.info(f"【{self.pure_user_id}】DrissionPage 兜底：账号锁已获取")

        # 启动前清理孤儿 Singleton 锁（已持账号锁，清理安全）
        self._clean_singleton_lock_files()

        try:
            self._launch_browser()
        except Exception:
            # 启动失败需释放已占用的锁与槽位
            self.close()
            raise

    # ==================== 浏览器启动与清理 ====================

    def _launch_browser(self) -> None:
        """启动 DrissionPage 控制的 Chromium。"""
        co = ChromiumOptions()

        # 复用 Playwright 的 chromium 二进制，保证 profile 格式兼容
        ensure_playwright_browser_path()
        chromium_path = get_chromium_executable_path()
        if chromium_path:
            co.set_browser_path(chromium_path)
            logger.info(f"【{self.pure_user_id}】DrissionPage 使用 chromium: {chromium_path}")
        else:
            logger.warning(f"【{self.pure_user_id}】未定位到 Playwright chromium，使用系统默认浏览器")

        # 复用本地化用户数据目录（方案 A）
        co.set_user_data_path(self.user_data_dir)
        # 自动分配调试端口，避免冲突
        co.set_argument("--remote-debugging-port=0")
        co.headless(on_off=self.headless)
        co.no_imgs(True)

        for arg in (
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
            "--disable-blink-features=AutomationControlled",
            "--disable-extensions",
            "--no-first-run",
            "--disable-default-apps",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-ipc-flooding-protection",
            "--window-size=1920,1080",
        ):
            co.set_argument(arg)

        logger.info(f"【{self.pure_user_id}】DrissionPage 启动浏览器（无头={self.headless}）...")
        self.browser = Chromium(co)
        self.page = self.browser.latest_tab
        logger.info(f"【{self.pure_user_id}】DrissionPage 浏览器启动成功")

    def _clean_singleton_lock_files(self) -> None:
        """清理 user_data_dir 中残留的 Chrome Singleton 锁文件。

        仅在已持有账号级互斥锁时调用，此时发现的任何 Singleton* 文件都是孤儿，
        删除可避免下次启动因 PROFILE_IN_USE（exit code 21）失败。
        """
        try:
            if not self.user_data_dir or not os.path.isdir(self.user_data_dir):
                return
            for fname in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                fpath = os.path.join(self.user_data_dir, fname)
                if not (os.path.exists(fpath) or os.path.islink(fpath)):
                    continue
                try:
                    if os.path.islink(fpath):
                        os.unlink(fpath)
                    else:
                        os.remove(fpath)
                    logger.warning(f"【{self.pure_user_id}】已清理残留 Chrome 锁文件: {fpath}")
                except Exception as inner_e:
                    logger.warning(f"【{self.pure_user_id}】清理 {fname} 失败（可忽略）: {inner_e}")
        except Exception as e:
            logger.warning(f"【{self.pure_user_id}】清理 Singleton 锁文件出错（可忽略）: {e}")

    # ==================== cookie 注入与导出 ====================

    def set_cookies_from_string(self, cookies_str: str) -> None:
        """将 cookie 字符串注入浏览器（覆盖目录中的旧 cookie，保证使用最新 cookie）。"""
        if not cookies_str:
            logger.warning(f"【{self.pure_user_id}】cookie 为空，跳过注入")
            return
        cookies_dict = trans_cookies(cookies_str)
        for name, value in cookies_dict.items():
            try:
                self.page.set.cookies({
                    "name": name,
                    "value": value,
                    "domain": ".goofish.com",
                    "path": "/",
                })
            except Exception as e:
                logger.warning(f"【{self.pure_user_id}】注入 cookie 失败 {name}: {e}")
        self.cookies = cookies_dict
        logger.info(f"【{self.pure_user_id}】已注入 {len(cookies_dict)} 个 cookie")

    def get_cookies_dict(self) -> Dict[str, str]:
        """从浏览器导出当前全部 cookie 为字典。"""
        result: Dict[str, str] = {}
        try:
            for cookie in self.page.cookies():
                if isinstance(cookie, dict) and "name" in cookie and "value" in cookie:
                    result[cookie["name"]] = cookie["value"]
        except Exception as e:
            logger.warning(f"【{self.pure_user_id}】导出 cookie 失败: {e}")
        return result

    # ==================== 滑块处理 ====================

    def _detect_blocked(self) -> bool:
        """检测页面是否仍处于验证拦截状态。"""
        try:
            return self.page.title == self.BLOCKED_TITLE
        except Exception:
            return False

    def _calculate_slide_distance(self) -> int:
        """动态计算滑动距离（委托 drissionpage_motion）。"""
        return calculate_slide_distance(self.page, self.pure_user_id)

    def _slide(self) -> None:
        """执行一次拟人化滑动（三段循环策略：谨慎/急躁/反思）。"""
        self.slide_attempt += 1
        cycle_position = (self.slide_attempt - 1) % 3
        cycle_number = (self.slide_attempt - 1) // 3 + 1
        is_impatient = cycle_position == 1

        if cycle_position == 0:
            target_total_time = random.uniform(1.5, 4.0)
            trajectory_points = random.randint(60, 150)
            mode = "谨慎模式"
            # 从第二轮起的谨慎阶段，按概率决定下次刷新页面
            if cycle_number > 1:
                refresh_prob = min(0.2 + (cycle_number - 2) * 0.15, 0.7)
                self.refresh_next = random.random() < refresh_prob
        elif cycle_position == 1:
            base_speed = max(0.2, 1.0 - cycle_number * 0.1)
            target_total_time = random.uniform(base_speed, base_speed + 0.4)
            trajectory_points = random.randint(30, 60)
            mode = "急躁模式"
        else:
            target_total_time = random.uniform(1.0, 2.0)
            trajectory_points = random.randint(50, 90)
            mode = "反思模式"

        logger.info(f"【{self.pure_user_id}】滑块第 {self.slide_attempt} 次（{mode}）")

        ele = self.page.wait.eles_loaded(self.SLIDER_LOADED_SELECTOR, timeout=10)
        if not ele:
            logger.warning(f"【{self.pure_user_id}】未找到滑块元素")
            return

        slider = self.page.ele(self.SLIDER_SELECTOR)
        time.sleep(random.uniform(0.1, 0.5) if is_impatient else random.uniform(0.8, 2.0))

        try:
            slider.hover()
            time.sleep(random.uniform(0.05, 0.3))
            self.page.actions.hold(slider)
            time.sleep(random.uniform(0.05, 0.3))
        except Exception as e:
            logger.warning(f"【{self.pure_user_id}】hover/hold 失败: {e}")
            try:
                self.page.actions.hold(slider)
            except Exception as hold_e:
                logger.error(f"【{self.pure_user_id}】hold 失败: {hold_e}")
                return

        distance = self._calculate_slide_distance()
        tracks = generate_tracks(distance, target_points=trajectory_points)
        execute_tracks(self.page, tracks, target_total_time, self.pure_user_id)

        # 释放前确认停顿
        time.sleep(random.uniform(0.05, 0.2) if is_impatient else random.uniform(0.2, 0.8))
        try:
            self.page.actions.release()
        except Exception as e:
            logger.warning(f"【{self.pure_user_id}】release 失败: {e}")
        time.sleep(random.uniform(0.3, 0.8))

    # ==================== 主入口 ====================

    def run(self, url: str, existing_cookies_str: str = "") -> Tuple[bool, Optional[Dict[str, str]]]:
        """执行滑块验证，返回 (是否成功, cookies 字典 | None)。"""
        start_time = time.time()
        try:
            if existing_cookies_str:
                self.set_cookies_from_string(existing_cookies_str)

            for attempt in range(self.max_retries):
                if time.time() - start_time > self.browser_timeout:
                    logger.warning(f"【{self.pure_user_id}】DrissionPage 兜底超时，停止重试")
                    break

                try:
                    if attempt == 0:
                        logger.info(f"【{self.pure_user_id}】DrissionPage 打开验证页面")
                        self.page.get(url)
                        time.sleep(random.uniform(1, 3))
                    elif self.refresh_next:
                        logger.info(f"【{self.pure_user_id}】DrissionPage 刷新页面重试")
                        self.page.refresh()
                        time.sleep(random.uniform(2, 4))
                        self.refresh_next = False
                    else:
                        logger.info(f"【{self.pure_user_id}】DrissionPage 不刷新，直接重试")
                        time.sleep(random.uniform(1, 2))

                    self._slide()

                    if not self._detect_blocked():
                        cookies = self.get_cookies_dict()
                        if cookies:
                            duration = time.time() - start_time
                            logger.info(
                                f"【{self.pure_user_id}】DrissionPage 兜底成功，耗时 {duration:.2f}s，"
                                f"滑动 {self.slide_attempt} 次"
                            )
                            return True, cookies
                        logger.warning(f"【{self.pure_user_id}】验证通过但未获取到 cookie")
                    else:
                        logger.warning(
                            f"【{self.pure_user_id}】第 {attempt + 1} 次滑动未通过（标题: {self.page.title}）"
                        )
                except Exception as e:
                    logger.error(f"【{self.pure_user_id}】DrissionPage 第 {attempt + 1} 次异常: {e}")

            logger.error(f"【{self.pure_user_id}】DrissionPage 兜底最终失败")
            return False, None
        finally:
            self.close()

    # ==================== 资源释放 ====================

    def _release_slot(self) -> None:
        if self._slot_acquired:
            try:
                concurrency_manager.unregister_instance(self.user_id)
            except Exception as e:
                logger.warning(f"【{self.pure_user_id}】释放并发槽位失败: {e}")
            finally:
                self._slot_acquired = False

    def close(self) -> None:
        """关闭浏览器并释放账号锁与并发槽位。"""
        try:
            if self.browser is not None:
                try:
                    self.browser.quit()
                except Exception as e:
                    logger.warning(f"【{self.pure_user_id}】关闭 DrissionPage 浏览器失败: {e}")
                finally:
                    self.browser = None
                    self.page = None
        finally:
            if self._account_lock_acquired:
                try:
                    account_browser_lock_manager.release(self.pure_user_id)
                except Exception as e:
                    logger.warning(f"【{self.pure_user_id}】释放账号锁失败: {e}")
                finally:
                    self._account_lock_acquired = False
            self._release_slot()


def run_drissionpage_verification(
    user_id: str,
    url: str,
    existing_cookies_str: str = "",
    headless: bool = True,
    browser_timeout: int = 25,
) -> Tuple[bool, Optional[Dict[str, str]]]:
    """模块级入口：在独立线程中运行 DrissionPage 兜底验证。

    Args:
        user_id: 用户/账号 ID
        url: 验证页面 URL
        existing_cookies_str: 现有 cookie 字符串（注入浏览器）
        headless: 是否无头
        browser_timeout: 单次验证超时（秒）

    Returns:
        (是否成功, cookies 字典 | None)
    """
    if not DRISSIONPAGE_AVAILABLE:
        logger.warning(f"【{user_id}】DrissionPage 未安装，跳过兜底")
        return False, None

    service = None
    try:
        service = DrissionPageSliderService(
            user_id=user_id,
            headless=headless,
            browser_timeout=browser_timeout,
        )
        return service.run(url, existing_cookies_str=existing_cookies_str)
    except Exception as e:
        logger.error(f"【{user_id}】DrissionPage 兜底执行失败: {e}")
        # __init__ 失败时 close 已在内部调用；此处兜底确保释放
        if service is not None:
            try:
                service.close()
            except Exception:
                pass
        return False, None
