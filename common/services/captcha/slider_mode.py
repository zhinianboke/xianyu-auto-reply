"""
滑块滑动方式运行时配置。

功能：
1. 从系统设置表读取滑块滑动方式
2. 在线程安全的进程缓存中保存当前方式
3. 为同步滑块编排器提供实时读取结果
"""
from __future__ import annotations

from threading import RLock

from loguru import logger
from sqlalchemy import select

from common.db.session import async_session_maker
from common.models.system_setting import SystemSetting


SLIDER_MODE_SETTING_KEY = "captcha.slider_mode"
SLIDER_MODE_BROWSER = "browser"
SLIDER_MODE_REAL_MOUSE = "real_mouse"
SLIDER_MODES = {SLIDER_MODE_BROWSER, SLIDER_MODE_REAL_MOUSE}

_mode_lock = RLock()
_current_mode = SLIDER_MODE_BROWSER


def normalize_slider_mode(value: object) -> str:
    """规范化滑块方式，非法值按浏览器自动滑动处理。"""
    mode = str(value or "").strip().lower()
    return mode if mode in SLIDER_MODES else SLIDER_MODE_BROWSER


def set_slider_mode(mode: object) -> str:
    """更新当前进程使用的滑块方式并返回规范值。"""
    normalized = normalize_slider_mode(mode)
    global _current_mode
    with _mode_lock:
        _current_mode = normalized
    return normalized


def get_slider_mode() -> str:
    """返回当前进程缓存的滑块方式。"""
    with _mode_lock:
        return _current_mode


def is_real_mouse_slider_mode(mode: object | None = None) -> bool:
    """指定方式或当前缓存是否使用真实鼠标滑动。"""
    selected_mode = get_slider_mode() if mode is None else normalize_slider_mode(mode)
    return selected_mode == SLIDER_MODE_REAL_MOUSE


async def refresh_slider_mode_from_database() -> str:
    """从数据库刷新滑块方式，读取失败时保留当前值。"""
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(SystemSetting.value).where(
                    SystemSetting.key == SLIDER_MODE_SETTING_KEY
                )
            )
            stored_mode = result.scalar_one_or_none()
        previous_mode = get_slider_mode()
        current_mode = set_slider_mode(stored_mode)
        if current_mode != previous_mode:
            logger.info(f"滑块滑动方式已实时切换为: {current_mode}")
        return current_mode
    except Exception as exc:
        logger.error(f"从数据库刷新滑块滑动方式失败，继续使用当前方式: {exc}")
        return get_slider_mode()
