"""
滑块验证失败冷却管理（websocket 进程内内存态）

功能：
1. 滑块验证失败后，按 cookie_id 进入指数退避冷却期
2. 冷却期内 refresh_token 检测到 punish 时跳过 handle_captcha_verification，
   不再启动 chromium，避免"视觉通过但风控不放行"时的无脑重试烧 CPU
3. 滑块验证成功（或风控解除）立即清零；冷却到期后下一次探测若成功同样清零

冷却序列（指数退避，封顶 30 分钟）：120s → 240s → 480s → 960s → 1800s → 1800s …

说明：
- 仅保存在 websocket 进程内存中（重启进程即清空），用于避免高频重启浏览器。
- 以 cookie_id 为键，多账号互不影响。
- 与 common/services/account_cooldown.py 区别：后者是 scheduler 进程专用、面向采集
  轮询的账号级冷却；本模块专治 websocket 进程滑块验证失败的高频重试，二者互不干扰。
"""
from __future__ import annotations

import threading
import time
from typing import Dict

# 首次失败冷却时长（秒）：2 分钟
BASE_COOLDOWN = 120
# 冷却时长上限（秒）：30 分钟
MAX_COOLDOWN = 1800


class SliderFailCooldownManager:
    """滑块验证失败冷却管理器（线程安全单例）。

    状态：
        _fail_count[cookie_id]    连续失败次数
        _cooldown_until[cookie_id] 冷却到期时间戳（epoch 秒）
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._lock = threading.Lock()
        self._fail_count: Dict[str, int] = {}
        self._cooldown_until: Dict[str, float] = {}
        self._initialized = True

    def _now(self) -> float:
        """当前时间戳（测试可替换以避免真实 sleep）。"""
        return time.time()

    @staticmethod
    def _cooldown_for(fail_count: int) -> float:
        """根据连续失败次数计算本次冷却时长（指数退避，封顶 MAX_COOLDOWN）。"""
        if fail_count <= 0:
            return 0.0
        return float(min(BASE_COOLDOWN * (2 ** (fail_count - 1)), MAX_COOLDOWN))

    def mark_fail(self, cookie_id: str) -> float:
        """记录一次滑块验证失败，进入/延长冷却期。

        Returns:
            本次冷却时长（秒）。
        """
        if not cookie_id:
            return 0.0
        key = str(cookie_id)
        with self._lock:
            count = self._fail_count.get(key, 0) + 1
            self._fail_count[key] = count
            cooldown = self._cooldown_for(count)
            self._cooldown_until[key] = self._now() + cooldown
            return cooldown

    def is_cooling(self, cookie_id: str) -> bool:
        """该账号当前是否处于滑块失败冷却期。"""
        if not cookie_id:
            return False
        key = str(cookie_id)
        with self._lock:
            return self._cooldown_until.get(key, 0.0) > self._now()

    def remaining(self, cookie_id: str) -> float:
        """冷却剩余秒数（不在冷却期返回 0，日志用）。"""
        if not cookie_id:
            return 0.0
        key = str(cookie_id)
        with self._lock:
            left = self._cooldown_until.get(key, 0.0) - self._now()
            return left if left > 0 else 0.0

    def clear(self, cookie_id: str) -> None:
        """滑块验证成功（或风控解除）时清零失败计数与冷却。"""
        if not cookie_id:
            return
        key = str(cookie_id)
        with self._lock:
            self._fail_count.pop(key, None)
            self._cooldown_until.pop(key, None)

    def reset(self) -> None:
        """清空所有账号的冷却状态（主要用于测试与进程重启场景）。"""
        with self._lock:
            self._fail_count.clear()
            self._cooldown_until.clear()


slider_fail_cooldown_manager = SliderFailCooldownManager()

__all__ = [
    "SliderFailCooldownManager",
    "slider_fail_cooldown_manager",
    "BASE_COOLDOWN",
    "MAX_COOLDOWN",
]
