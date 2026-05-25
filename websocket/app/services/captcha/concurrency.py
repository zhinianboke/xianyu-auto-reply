"""
并发管理模块 - 兼容层

从 common.services.captcha.concurrency 重新导出
"""
from common.services.captcha.concurrency import (
    DisabledAccountManager,
    disabled_account_manager,
    is_account_disabled_in_db,
    should_skip_account,
    BrowserSlotManager,
    acquire_browser_slot,
    release_browser_slot,
    get_browser_stats,
    SliderConcurrencyManager,
    concurrency_manager,
)

__all__ = [
    "DisabledAccountManager",
    "disabled_account_manager",
    "is_account_disabled_in_db",
    "should_skip_account",
    "BrowserSlotManager",
    "acquire_browser_slot",
    "release_browser_slot",
    "get_browser_stats",
    "SliderConcurrencyManager",
    "concurrency_manager",
]
