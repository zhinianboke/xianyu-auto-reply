"""
闲鱼滑块验证服务模块 - 兼容层

从 common.services.captcha.xianyu_slider_stealth 重新导出
"""
from common.services.captcha.xianyu_slider_stealth import (
    BaxiaPunishCaptchaException,
    LoginPageErrorException,
    XianyuSliderStealth,
    run_slider_verification,
)

__all__ = [
    "BaxiaPunishCaptchaException",
    "LoginPageErrorException",
    "XianyuSliderStealth",
    "run_slider_verification",
]
