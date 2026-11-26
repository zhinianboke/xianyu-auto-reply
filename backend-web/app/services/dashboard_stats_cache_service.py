"""
管理员仪表盘统计缓存服务。

功能：
1. 为管理员全局仪表盘统计提供短TTL内存缓存。
2. 分开缓存公用总数与管理员统计，三个接口可共用所需的数据。
3. 为当前登录管理员的额度状态提供短TTL缓存，减少重复查询。
"""
from __future__ import annotations

import asyncio
import time
from copy import deepcopy
from datetime import date
from typing import Any, Awaitable, Callable, Literal, TypeVar

SnapshotName = Literal["global_totals", "admin_overview", "admin_today"]
SnapshotValue = TypeVar("SnapshotValue", bound=dict)


class DashboardStatsCacheService:
    """管理员仪表盘统计短TTL缓存服务。"""

    _snapshot_locks = {
        "global_totals": asyncio.Lock(),
        "admin_overview": asyncio.Lock(),
        "admin_today": asyncio.Lock(),
    }
    _snapshots: dict[SnapshotName, dict[str, Any]] = {}
    _snapshot_ttl_seconds = 3

    _user_limit_lock = asyncio.Lock()
    _user_limit_cache: dict[int, dict[str, Any]] = {}
    _user_limit_ttl_seconds = 3

    @classmethod
    def _is_valid(cls, record: dict[str, Any], *, snapshot_day: date | None = None) -> bool:
        """检查缓存是否仍在有效期内，含日期的统计需与请求日期相同。"""
        return record.get("snapshot_day") == snapshot_day and record["expires_at"] > time.monotonic()

    @classmethod
    async def get_snapshot(
        cls,
        name: SnapshotName,
        loader: Callable[[], Awaitable[SnapshotValue]],
        *,
        snapshot_day: date | None = None,
    ) -> SnapshotValue:
        """按快照名称合并并发查询，使用传入的加载函数，返回独立的统计结果。"""
        cached = cls._snapshots.get(name)
        if cached is not None and cls._is_valid(cached, snapshot_day=snapshot_day):
            return deepcopy(cached["value"])

        async with cls._snapshot_locks[name]:
            cached = cls._snapshots.get(name)
            if cached is not None and cls._is_valid(cached, snapshot_day=snapshot_day):
                return deepcopy(cached["value"])

            value = await loader()
            cls._snapshots[name] = {
                "value": deepcopy(value),
                "snapshot_day": snapshot_day,
                "expires_at": time.monotonic() + cls._snapshot_ttl_seconds,
            }
            return deepcopy(value)

    @classmethod
    async def get_user_limit_status(
        cls,
        user_id: int,
        loader: Callable[[], Awaitable[dict[str, int | None]]],
    ) -> dict[str, int | None]:
        cached = cls._user_limit_cache.get(user_id)
        if cached is not None and cls._is_valid(cached):
            return deepcopy(cached["value"])

        async with cls._user_limit_lock:
            cls._cleanup_user_limit_cache_locked()
            cached = cls._user_limit_cache.get(user_id)
            if cached is not None and cls._is_valid(cached):
                return deepcopy(cached["value"])

            value = await loader()
            cls._user_limit_cache[user_id] = {
                "value": deepcopy(value),
                "expires_at": time.monotonic() + cls._user_limit_ttl_seconds,
            }
            return deepcopy(value)

    @classmethod
    def _cleanup_user_limit_cache_locked(cls) -> None:
        expired_user_ids = [
            user_id
            for user_id, record in cls._user_limit_cache.items()
            if not cls._is_valid(record)
        ]
        for user_id in expired_user_ids:
            cls._user_limit_cache.pop(user_id, None)
