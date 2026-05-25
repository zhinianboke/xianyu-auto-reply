"""
管理员仪表盘统计缓存服务。

功能：
1. 为管理员全局仪表盘统计提供短TTL内存缓存。
2. 让 /admin/stats 与 /admin/stats/today 共享同一份全局统计快照。
3. 为当前登录管理员的额度状态提供短TTL缓存，减少重复查询。
"""
from __future__ import annotations

import asyncio
import time
from copy import deepcopy
from typing import Any, Awaitable, Callable


class DashboardStatsCacheService:
    """管理员仪表盘统计短TTL缓存服务。"""

    _admin_bundle_lock = asyncio.Lock()
    _admin_bundle_cache: dict[str, Any] | None = None
    _admin_bundle_ttl_seconds = 3

    _user_limit_lock = asyncio.Lock()
    _user_limit_cache: dict[int, dict[str, Any]] = {}
    _user_limit_ttl_seconds = 3

    @classmethod
    def _is_valid(cls, record: dict[str, Any] | None) -> bool:
        if not record:
            return False
        return float(record.get("expires_at") or 0) > time.time()

    @classmethod
    async def get_admin_bundle(
        cls,
        loader: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        cached = cls._admin_bundle_cache
        if cls._is_valid(cached):
            return deepcopy(cached["value"])

        async with cls._admin_bundle_lock:
            cached = cls._admin_bundle_cache
            if cls._is_valid(cached):
                return deepcopy(cached["value"])

            value = await loader()
            cls._admin_bundle_cache = {
                "value": deepcopy(value),
                "expires_at": time.time() + cls._admin_bundle_ttl_seconds,
            }
            return deepcopy(value)

    @classmethod
    async def get_user_limit_status(
        cls,
        user_id: int,
        loader: Callable[[], Awaitable[dict[str, int | None]]],
    ) -> dict[str, int | None]:
        cached = cls._user_limit_cache.get(user_id)
        if cls._is_valid(cached):
            return deepcopy(cached["value"])

        async with cls._user_limit_lock:
            cls._cleanup_user_limit_cache_locked()
            cached = cls._user_limit_cache.get(user_id)
            if cls._is_valid(cached):
                return deepcopy(cached["value"])

            value = await loader()
            cls._user_limit_cache[user_id] = {
                "value": deepcopy(value),
                "expires_at": time.time() + cls._user_limit_ttl_seconds,
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
