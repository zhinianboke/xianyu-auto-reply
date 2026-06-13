"""
发货冷却管理器

功能：
1. 基于 Redis 的订单级冷却（多实例安全）
2. Redis 不可用时降级为内存缓存
3. 支持 TTL 和手动清除
"""
from __future__ import annotations

import time
from typing import Optional

from loguru import logger


class DeliveryCooldown:
    """
    订单发货冷却管理器，防止同一订单重复发货。
    优先使用 Redis（多实例安全），降级为内存缓存。
    """

    _instance: Optional["DeliveryCooldown"] = None

    def __init__(self):
        self._memory_cache: dict[str, float] = {}  # order_id -> expire_ts
        self._redis_client = None
        self._redis_checked = False

    @classmethod
    def get_instance(cls) -> "DeliveryCooldown":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _get_redis(self):
        """延迟获取 Redis 客户端"""
        if not self._redis_checked:
            self._redis_checked = True
            try:
                from common.db.redis_client import get_redis_client
                self._redis_client = await get_redis_client()
                await self._redis_client.ping()
                logger.info("DeliveryCooldown: Redis 连接成功")
            except Exception as e:
                logger.warning(f"DeliveryCooldown: Redis 不可用，降级为内存缓存: {e}")
                self._redis_client = None
        return self._redis_client

    async def check(self, order_id: str) -> bool:
        """检查订单是否在冷却中"""
        redis = await self._get_redis()
        if redis:
            try:
                return await redis.exists(f"delivery_cooldown:{order_id}") > 0
            except Exception as e:
                logger.warning(f"DeliveryCooldown Redis check 失败: {e}")
                # 降级到内存
        return self._check_memory(order_id)

    async def set(self, order_id: str, ttl: int = 600):
        """设置冷却（默认 10 分钟）"""
        redis = await self._get_redis()
        if redis:
            try:
                await redis.setex(f"delivery_cooldown:{order_id}", ttl, "1")
                return
            except Exception as e:
                logger.warning(f"DeliveryCooldown Redis set 失败: {e}")
        self._set_memory(order_id, ttl)

    async def clear(self, order_id: str):
        """手动清除冷却"""
        redis = await self._get_redis()
        if redis:
            try:
                await redis.delete(f"delivery_cooldown:{order_id}")
            except Exception:
                pass
        self._memory_cache.pop(order_id, None)

    async def clear_all(self):
        """清除所有冷却（仅内存，Redis 按前缀批量删除）"""
        self._memory_cache.clear()
        redis = await self._get_redis()
        if redis:
            try:
                keys = []
                async for key in redis.scan_iter("delivery_cooldown:*"):
                    keys.append(key)
                if keys:
                    await redis.delete(*keys)
            except Exception as e:
                logger.warning(f"DeliveryCooldown Redis clear_all 失败: {e}")

    def _check_memory(self, order_id: str) -> bool:
        expire_ts = self._memory_cache.get(order_id)
        if expire_ts is None:
            return False
        if time.time() > expire_ts:
            self._memory_cache.pop(order_id, None)
            return False
        return True

    def _set_memory(self, order_id: str, ttl: int):
        self._memory_cache[order_id] = time.time() + ttl
        # 清理过期条目（防止内存膨胀）
        if len(self._memory_cache) > 1000:
            now = time.time()
            expired = [k for k, v in self._memory_cache.items() if now > v]
            for k in expired:
                self._memory_cache.pop(k, None)

    @staticmethod
    def get() -> "DeliveryCooldown":
        """便捷获取单例"""
        return DeliveryCooldown.get_instance()


# 模块级便捷实例
delivery_cooldown = DeliveryCooldown.get()
