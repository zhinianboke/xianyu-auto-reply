"""
滑块验证服务模块 - 兼容层

从 common.services.captcha.slider_stealth 重新导出
"""
from common.services.captcha.slider_stealth import (
    PlaywrightSliderService,
    get_slider_stats,
    run_slider_verification,
)
from common.services.captcha.orchestrator import run_slider_verification_with_fallback

__all__ = [
    "PlaywrightSliderService",
    "get_slider_stats",
    "run_slider_verification",
    "run_slider_verification_with_fallback",
]
