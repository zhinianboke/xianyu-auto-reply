"""
浏览器特征和反检测脚本

提供 Playwright 滑块浏览器特征和最小化自动化标记隐藏脚本。

原则：尽量保留 Chromium 原生值。伪造 UA、屏幕、插件、Canvas、WebGL 或时间 API
容易产生互相矛盾的指纹，实际比只隐藏明确的自动化标记更容易触发风控。
"""
from __future__ import annotations

from typing import Any, Dict


def get_random_browser_features() -> Dict[str, Any]:
    """返回与 Playwright 启动上下文一致的稳定特征配置。"""
    return {
        'window_size': '1920,1080',
        'lang': 'zh-CN',
        'accept_lang': 'zh-CN,zh;q=0.9,en;q=0.8',
        'locale': 'zh-CN',
        'viewport_width': 1920,
        'viewport_height': 1080,
        'device_scale_factor': 1.0,
        'is_mobile': False,
        'has_touch': False,
        'timezone_id': 'Asia/Shanghai'
    }


def get_stealth_script(browser_features: Dict[str, Any]) -> str:
    """返回最小化隐藏脚本，保留浏览器原生指纹与时间行为。"""
    _ = browser_features
    return """
        try {
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
            delete Object.getPrototypeOf(navigator).webdriver;
        } catch (e) {}
        try {
            delete window.playwright;
            delete window.__playwright;
            delete window.__pw_manual;
            delete window.__PW_inspect;
        } catch (e) {}
    """

