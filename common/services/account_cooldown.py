"""
账号风控冷却管理（进程内内存态）

功能：
1. 记录因触发风控（被挤爆/验证/punish 等）的账号，进入冷却期（默认 20 分钟）
2. 采集等定时任务轮询账号时，过滤掉处于冷却期的账号
3. 当所有账号都在冷却期时，调用方可据此跳过本次采集并记录失败原因

说明：
- 冷却状态仅保存在 scheduler 进程内存中（重启后清空），用于短时风控规避，不入库。
- 以 account_id 为键全局共享，避免同一账号被不同任务同时频繁使用而持续触发风控。
"""
from __future__ import annotations

import time
from threading import Lock
from typing import Dict, List, Optional, Sequence

# 触发风控/被挤爆/验证等标志：命中则将账号加入冷却（与 xianyu_mtop 的风控判定保持一致）
_RISK_MARKERS = (
    "FAIL_SYS_USER_VALIDATE",
    "RGV587",
    "FAIL_SYS_ILLEGAL_ACCESS",
    "哎哟喂",
    "挤爆",
    "punish",
    "captcha",
    "validate",
)

# 默认冷却时长（秒）：被挤爆/触发验证后 20 分钟内不再使用该账号
DEFAULT_COOLDOWN_SECONDS = 1200


class AccountCooldownManager:
    """账号风控冷却管理器（进程内单例使用）。"""

    def __init__(self) -> None:
        # account_id -> 冷却结束时间（epoch 秒）
        self._cooldowns: Dict[str, float] = {}
        self._lock = Lock()

    @staticmethod
    def is_risk_control_error(error: Optional[str]) -> bool:
        """判断错误信息是否属于风控/被挤爆/验证类（需冷却该账号）。"""
        if not error:
            return False
        text = str(error)
        return any(marker in text for marker in _RISK_MARKERS)

    def add(self, account_id: str, seconds: int = DEFAULT_COOLDOWN_SECONDS) -> None:
        """将账号加入冷却期（自当前时间起 seconds 秒）。"""
        if not account_id:
            return
        with self._lock:
            self._cooldowns[str(account_id)] = time.time() + max(seconds, 0)

    def clear(self, account_id: str) -> bool:
        """解除账号冷却（如外部回传新 Cookie 后立即恢复该账号可用，无需等满冷却期）。

        Returns:
            True 表示该账号原本处于冷却期且已被解除；False 表示原本就不在冷却期。
        """
        if not account_id:
            return False
        with self._lock:
            return self._cooldowns.pop(str(account_id), None) is not None

    def is_cooling(self, account_id: str) -> bool:
        """账号当前是否处于冷却期。"""
        with self._lock:
            return self._cooldowns.get(str(account_id), 0.0) > time.time()

    def filter_available(self, account_ids: Sequence[str]) -> List[str]:
        """返回未处于冷却期的账号ID列表（保持入参顺序）。"""
        now = time.time()
        with self._lock:
            return [aid for aid in account_ids if self._cooldowns.get(str(aid), 0.0) <= now]


# 全局单例（scheduler 进程内共享）
account_cooldown_manager = AccountCooldownManager()

__all__ = ["AccountCooldownManager", "account_cooldown_manager", "DEFAULT_COOLDOWN_SECONDS"]
