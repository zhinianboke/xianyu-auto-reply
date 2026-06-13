"""
AI客户端连接池

缓存并复用AI服务客户端实例，避免每次请求都创建新连接。

支持的服务商：
- OpenAI兼容（AsyncOpenAI客户端）
- Anthropic（httpx.AsyncClient）
- Gemini（httpx.AsyncClient）
- DashScope应用（httpx.AsyncClient）

特性：
- 按 (provider_type, base_url, api_key_prefix) 缓存客户端
- asyncio.Lock 保证线程安全
- 自动清理空闲客户端（可配置TTL，默认1小时）
- close_all() 优雅关闭
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional, Tuple

import httpx
from loguru import logger


# 缓存键: (provider_type, normalized_base_url, api_key_prefix)
_CacheKey = Tuple[str, str, str]


def _api_key_prefix(api_key: str, length: int = 8) -> str:
    """取 api_key 前 N 位作为缓存区分标识"""
    return (api_key or "")[:length]


def _make_cache_key(provider_type: str, base_url: str, api_key: str) -> _CacheKey:
    """构造缓存键"""
    return (provider_type, (base_url or "").rstrip("/"), _api_key_prefix(api_key))


class _CacheEntry:
    """缓存条目，包含客户端实例和最后使用时间"""

    __slots__ = ("client", "last_used")

    def __init__(self, client: Any) -> None:
        self.client = client
        self.last_used: float = time.monotonic()

    def touch(self) -> None:
        self.last_used = time.monotonic()


class AIClientPool:
    """AI客户端连接池（单例）"""

    _instance: Optional["AIClientPool"] = None

    def __init__(self, ttl_seconds: float = 3600.0) -> None:
        self._pool: Dict[_CacheKey, _CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl_seconds
        logger.info(f"AI客户端连接池初始化完成 (TTL={ttl_seconds}s)")

    @classmethod
    def get_instance(cls, ttl_seconds: float = 3600.0) -> "AIClientPool":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = AIClientPool(ttl_seconds=ttl_seconds)
        return cls._instance

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def get_client(
        self,
        provider_type: str,
        base_url: str,
        api_key: str,
    ) -> Any:
        """
        获取（或复用）AI客户端实例。

        Args:
            provider_type: 服务商类型 (openai_compatible / anthropic / gemini / dashscope_app)
            base_url: API基础地址
            api_key: API密钥

        Returns:
            对应服务商的客户端实例
        """
        key = _make_cache_key(provider_type, base_url, api_key)

        async with self._lock:
            # 清理过期条目
            await self._evict_expired()

            entry = self._pool.get(key)
            if entry is not None:
                entry.touch()
                return entry.client

            # 创建新客户端
            client = self._create_client(provider_type, base_url, api_key)
            self._pool[key] = _CacheEntry(client)
            logger.debug(
                f"AIClientPool: 新建客户端: provider={provider_type}, "
                f"base_url={base_url}, pool_size={len(self._pool)}"
            )
            return client

    async def close_all(self) -> None:
        """关闭所有缓存的客户端（用于优雅退出）"""
        async with self._lock:
            for key, entry in self._pool.items():
                try:
                    client = entry.client
                    if hasattr(client, "close"):
                        await client.close()
                    elif hasattr(client, "aclose"):
                        await client.aclose()
                except Exception as exc:
                    logger.warning(f"AIClientPool: 关闭客户端失败: {key}, {exc}")
            count = len(self._pool)
            self._pool.clear()
            logger.info(f"AIClientPool: 已关闭全部客户端 ({count} 个)")

    async def remove_client(
        self,
        provider_type: str,
        base_url: str,
        api_key: str,
    ) -> None:
        """移除并关闭指定客户端（例如连接出错后强制重建）"""
        key = _make_cache_key(provider_type, base_url, api_key)
        async with self._lock:
            entry = self._pool.pop(key, None)
        if entry is not None:
            try:
                if hasattr(entry.client, "close"):
                    await entry.client.close()
                elif hasattr(entry.client, "aclose"):
                    await entry.client.aclose()
            except Exception:
                logger.debug("AIClientPool: failed to close client during remove")
            logger.debug(f"AIClientPool: 已移除客户端: provider={provider_type}")

    @property
    def pool_size(self) -> int:
        """当前缓存中的客户端数量"""
        return len(self._pool)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _evict_expired(self) -> None:
        """清理过期条目（调用前需持有 _lock）"""
        now = time.monotonic()
        expired = [
            key
            for key, entry in self._pool.items()
            if now - entry.last_used > self._ttl
        ]
        for key in expired:
            entry = self._pool.pop(key, None)
            if entry is not None:
                try:
                    if hasattr(entry.client, "close"):
                        await entry.client.close()
                    elif hasattr(entry.client, "aclose"):
                        await entry.client.aclose()
                except Exception:
                    logger.debug("AIClientPool: failed to close expired client")
        if expired:
            logger.debug(f"AIClientPool: 清理了 {len(expired)} 个过期客户端")

    @staticmethod
    def _create_client(
        provider_type: str,
        base_url: str,
        api_key: str,
    ) -> Any:
        """根据服务商类型创建客户端实例"""
        if provider_type == "openai_compatible":
            from openai import AsyncOpenAI
            from common.services.ai_provider_service import normalize_openai_base_url

            return AsyncOpenAI(
                api_key=api_key,
                base_url=normalize_openai_base_url(base_url),
            )

        if provider_type in ("anthropic", "gemini", "dashscope_app"):
            # 这三种在原代码中都是直接用 httpx.AsyncClient 发请求
            return httpx.AsyncClient(timeout=60)

        # 兜底：当作 OpenAI 兼容处理
        from openai import AsyncOpenAI
        from common.services.ai_provider_service import normalize_openai_base_url

        return AsyncOpenAI(
            api_key=api_key,
            base_url=normalize_openai_base_url(base_url),
        )


# 模块级便捷函数
def get_ai_client_pool(ttl_seconds: float = 3600.0) -> AIClientPool:
    """获取全局AI客户端连接池"""
    return AIClientPool.get_instance(ttl_seconds=ttl_seconds)

