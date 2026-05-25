"""
验证码服务模块导出（websocket）

从 common.services.captcha 重新导出，保持向后兼容。
由 __init__.py 通过 from ._exports import * 重新导出。
"""
from common.services.captcha import (
    SliderConcurrencyManager,
    concurrency_manager,
    RetryStrategyStats,
    strategy_stats,
    get_random_browser_features,
    get_stealth_script,
    TrajectoryGenerator,
    SliderElementFinder,
    VerificationChecker,
    HistoryManager,
    PlaywrightSliderService,
    get_slider_stats,
    run_slider_verification,
    disabled_account_manager,
    should_skip_account,
    acquire_browser_slot,
    release_browser_slot,
    get_browser_stats,
)

# 闲鱼扩展版
from common.services.captcha.xianyu_slider_stealth import XianyuSliderStealth

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
    "XianyuSliderStealth",
    "get_slider_stats",
    "run_slider_verification",
]
