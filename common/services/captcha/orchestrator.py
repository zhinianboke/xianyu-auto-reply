"""
滑块验证编排：主引擎 + DrissionPage 兜底

对外提供与 run_slider_verification 一致的返回契约 (是否成功, cookies 字典 | None)：
1. 先用 Playwright 主引擎（run_slider_verification）；
2. 主引擎成功且取得 x5sec cookie → 直接返回；
3. 否则（失败或无 x5sec）且兜底开关开启 → 调用 DrissionPage 兜底引擎重试一次。

调用方只需把目标函数从 run_slider_verification 换成本函数即可，无需关心引擎细节。
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from loguru import logger

from common.services.captcha.slider_stealth import run_slider_verification
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


def run_slider_verification_with_fallback(
    user_id: str,
    url: str,
    enable_learning: bool = True,
    headless: bool = False,
    browser_timeout: int = 20,
    existing_cookies_str: str = "",
) -> Tuple[bool, Optional[Dict[str, str]], Optional[str]]:
    """主引擎 + DrissionPage 兜底的滑块验证编排。

    Args:
        user_id: 用户/账号 ID
        url: 验证页面 URL
        enable_learning: 主引擎是否启用轨迹学习
        headless: 主引擎是否无头
        browser_timeout: 主引擎单次超时（秒）
        existing_cookies_str: 现有 cookie 字符串，供兜底引擎注入

    Returns:
        (是否成功, cookies 字典 | None, 通过引擎 | None)
        通过引擎取值：'playwright'（主引擎）/ 'drissionpage'（兜底引擎）/ None（未成功）
    """
    # 1. Playwright 主引擎
    ok, cookies = run_slider_verification(
        user_id, url, enable_learning, headless, browser_timeout
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
    logger.info(f"【{user_id}】主引擎滑块未通过，启用 DrissionPage 兜底引擎重试")
    ok2, cookies2 = run_drissionpage_verification(
        user_id, url, existing_cookies_str=existing_cookies_str,
        headless=fb_headless, browser_timeout=fb_timeout,
    )
    if ok2 and _has_x5sec(cookies2):
        return True, cookies2, "drissionpage"

    # 4. 兜底也未取得 x5sec：优先保留主引擎"成功但无 x5sec"的结果，
    #    以维持上层原有的"无 x5sec 不计入禁用"语义。
    if ok and cookies:
        return ok, cookies, "playwright"
    return ok2, cookies2, None
