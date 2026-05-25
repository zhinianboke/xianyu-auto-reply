"""
滑块验证服务模块 - 兼容层

从 common.services.captcha.slider_stealth 重新导出
"""
from common.services.captcha.slider_stealth import (
    PlaywrightSliderService,
    get_slider_stats,
    run_slider_verification,
)

__all__ = [
    "PlaywrightSliderService",
    "get_slider_stats",
    "run_slider_verification",
]
