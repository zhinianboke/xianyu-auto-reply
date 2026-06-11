"""
验证码服务模块导出

包含Playwright滑块验证功能，由 __init__.py 通过 from ._exports import * 重新导出。
"""
from common.services.captcha.concurrency import (
    SliderConcurrencyManager,
    concurrency_manager,
    disabled_account_manager,
    should_skip_account,
    acquire_browser_slot,
    release_browser_slot,
    get_browser_stats,
)
from common.services.captcha.strategy_stats import (
    RetryStrategyStats,
    strategy_stats,
)
from common.services.captcha.browser_features import (
    get_random_browser_features,
    get_stealth_script,
)
from common.services.captcha.trajectory import TrajectoryGenerator
from common.services.captcha.slider_elements import SliderElementFinder
from common.services.captcha.verification_checker import VerificationChecker
from common.services.captcha.history_manager import HistoryManager
from common.services.captcha.slider_stealth import (
    PlaywrightSliderService,
    get_slider_stats,
    run_slider_verification,
)
from common.services.captcha.drissionpage_slider import (
    DrissionPageSliderService,
    run_drissionpage_verification,
    DRISSIONPAGE_AVAILABLE,
)
from common.services.captcha.orchestrator import run_slider_verification_with_fallback

# 别名，兼容旧代码
SliderStealth = PlaywrightSliderService

__all__ = [
    # 并发管理
    "SliderConcurrencyManager",
    "concurrency_manager",
    "disabled_account_manager",
    "should_skip_account",
    "acquire_browser_slot",
    "release_browser_slot",
    "get_browser_stats",
    # 策略统计
    "RetryStrategyStats",
    "strategy_stats",
    # 浏览器特征
    "get_random_browser_features",
    "get_stealth_script",
    # 轨迹生成
    "TrajectoryGenerator",
    # 元素查找
    "SliderElementFinder",
    # 验证检查
    "VerificationChecker",
    # 历史管理
    "HistoryManager",
    # 主服务
    "PlaywrightSliderService",
    "SliderStealth",  # 别名
    "get_slider_stats",
    "run_slider_verification",
    # DrissionPage 兜底引擎
    "DrissionPageSliderService",
    "run_drissionpage_verification",
    "DRISSIONPAGE_AVAILABLE",
    "run_slider_verification_with_fallback",
]
