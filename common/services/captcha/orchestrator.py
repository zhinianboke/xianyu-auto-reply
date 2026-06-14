"""
滑块验证编排：主引擎 + DrissionPage 兜底

对外提供与 run_slider_verification 一致的返回契约 (是否成功, cookies 字典 | None)：
1. 先用 Playwright 主引擎（run_slider_verification）；
2. 主引擎成功且取得 x5sec cookie → 直接返回；
3. 否则（失败或无 x5sec）且兜底开关开启 → 调用 DrissionPage 兜底引擎重试一次。

调用方只需把目标函数从 run_slider_verification 换成本函数即可，无需关心引擎细节。
"""
from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from loguru import logger

from common.services.captcha.slider_stealth import run_slider_verification, CAPTCHA_NOT_REQUIRED
from common.services.captcha.drissionpage_slider import (
    run_drissionpage_verification,
    DRISSIONPAGE_AVAILABLE,
)


def _has_x5sec(cookies: Optional[Dict[str, str]]) -> bool:
    """判断 cookie 字典中是否包含 x5/x5sec 相关 cookie（与上层放行判定一致）。"""
    if not cookies:
        return False
    for name in cookies:
        name_lower = str(name).lower()
        if name_lower.startswith("x5") or "x5sec" in name_lower:
            return True
    return False


def _load_fallback_config() -> Tuple[bool, bool, int]:
    """读取兜底配置 (是否启用, 是否无头, 超时秒)。

    兼容从 websocket 的 app.core.config 或 common.core.config 读取。
    """
    enabled, headless, timeout = True, True, 25
    settings = None
    try:
        from app.core.config import get_settings
        settings = get_settings()
    except Exception:
        try:
            from common.core.config import get_settings
            settings = get_settings()
        except Exception:
            settings = None
    if settings is not None:
        enabled = bool(getattr(settings, "captcha_drissionpage_fallback_enabled", True))
        headless = bool(getattr(settings, "captcha_drissionpage_headless", True))
        timeout = int(getattr(settings, "captcha_drissionpage_timeout", 25))
    return enabled, headless, timeout


def _real_mouse_enabled() -> bool:
    """读取「真实鼠标模式」开关（默认 False；Docker/无头默认关闭）。"""
    settings = None
    try:
        from app.core.config import get_settings
        settings = get_settings()
    except Exception:
        try:
            from common.core.config import get_settings
            settings = get_settings()
        except Exception:
            settings = None
    if settings is None:
        return False
    return bool(getattr(settings, "captcha_real_mouse_enabled", False))


def run_slider_verification_with_fallback(
    user_id: str,
    url: str,
    enable_learning: bool = True,
    headless: bool = False,
    browser_timeout: int = 20,
    existing_cookies_str: str = "",
    url_provider: Optional[Callable[[], Optional[str]]] = None,
) -> Tuple[bool, Optional[Dict[str, str]], Optional[str]]:
    """主引擎 + DrissionPage 兜底的滑块验证编排。

    Args:
        user_id: 用户/账号 ID
        url: 验证页面 URL
        enable_learning: 主引擎是否启用轨迹学习
        headless: 主引擎是否无头
        browser_timeout: 主引擎单次超时（秒）
        existing_cookies_str: 现有 cookie 字符串，供兜底引擎注入
        url_provider: 可选回调，浏览器就绪后用于重新获取新鲜验证链接，规避等待槽位导致的链接过期

    Returns:
        (是否成功, cookies 字典 | None, 通过引擎 | None)
        通过引擎取值：'playwright'（主引擎）/ 'drissionpage'（兜底引擎）/ 'real_mouse'（真实鼠标）/ None（未成功）
    """
    # 0. 真实鼠标模式（可选，环境变量 CAPTCHA_REAL_MOUSE=true 开启）：
    #    用物理光标回放真人轨迹，成功率高但会占用桌面鼠标，仅限有桌面的 Windows。
    #    未开启 / 不可用（无头 Linux、依赖缺失）时自动跳过，走原有逻辑。
    if _real_mouse_enabled():
        try:
            from common.services.captcha.real_mouse_slider import (
                run_real_mouse_verification,
                REAL_MOUSE_AVAILABLE,
            )
            if REAL_MOUSE_AVAILABLE:
                logger.info(f"【{user_id}】启用真实鼠标滑块引擎")
                rm_ok, rm_cookies = run_real_mouse_verification(
                    user_id, url,
                    existing_cookies_str=existing_cookies_str,
                    browser_timeout=max(browser_timeout, 40),
                    url_provider=url_provider,
                )
                if rm_ok and _has_x5sec(rm_cookies):
                    return True, rm_cookies, "real_mouse"
                logger.info(f"【{user_id}】真实鼠标引擎未通过，回退原有滑块逻辑")
            else:
                logger.info(f"【{user_id}】真实鼠标引擎不可用（无桌面/依赖缺失），走原有逻辑")
        except Exception as rm_e:
            logger.warning(f"【{user_id}】真实鼠标引擎异常，回退原有逻辑: {rm_e}")

    # 1. Playwright 主引擎
    ok, cookies = run_slider_verification(
        user_id, url, enable_learning, headless, browser_timeout,
        url_provider=url_provider,
    )
    if ok and _has_x5sec(cookies):
        return True, cookies, "playwright"

    # 2. 判断是否需要兜底
    fallback_enabled, fb_headless, fb_timeout = _load_fallback_config()
    if not fallback_enabled or not DRISSIONPAGE_AVAILABLE:
        if not fallback_enabled:
            logger.info(f"【{user_id}】DrissionPage 兜底未启用，返回主引擎结果")
        return ok, cookies, ("playwright" if (ok and cookies) else None)

    # 3. DrissionPage 兜底
    # 兜底前同样尝试刷新链接，避免主引擎耗时后链接再次过期
    fb_url = url
    if url_provider is not None:
        try:
            fresh = url_provider()
            if fresh == CAPTCHA_NOT_REQUIRED:
                # token 已可用、风控已解除，无需滑块，跳过兜底引擎（由上层采用新 token）
                logger.info(f"【{user_id}】检测到 token 已可用，跳过 DrissionPage 兜底引擎")
                return ok, cookies, ("playwright" if (ok and cookies) else None)
            if fresh and isinstance(fresh, str):
                fb_url = fresh
                logger.info(f"【{user_id}】兜底引擎使用刷新后的验证链接")
        except Exception as up_e:
            logger.warning(f"【{user_id}】兜底前刷新验证链接失败，沿用原链接: {up_e}")

    logger.info(f"【{user_id}】主引擎滑块未通过，启用 DrissionPage 兜底引擎重试")
    ok2, cookies2 = run_drissionpage_verification(
        user_id, fb_url, existing_cookies_str=existing_cookies_str,
        headless=fb_headless, browser_timeout=fb_timeout,
    )
    if ok2 and _has_x5sec(cookies2):
        return True, cookies2, "drissionpage"

    # 4. 兜底也未取得 x5sec：优先保留主引擎"成功但无 x5sec"的结果，
    #    以维持上层原有的"无 x5sec 不计入禁用"语义。
    if ok and cookies:
        return ok, cookies, "playwright"
    return ok2, cookies2, None
