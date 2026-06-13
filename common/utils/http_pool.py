"""
共享 HTTP 连接池模块

提供全局单例 aiohttp.ClientSession，复用于所有通知和 HTTP 请求，
避免每次调用都创建新连接带来的开销。

用法:
    from common.utils.http_pool import http_pool

    # 直接调用便捷方法
    resp = await http_pool.get("https://example.com")
    resp = await http_pool.post("https://example.com", json={"key": "val"})
    resp = await http_pool.post("https://example.com", data={"key": "val"})

    # 或者手动获取 session
    session = await http_pool.get_session()

    # 应用退出时清理
    await http_pool.close()
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import aiohttp
from loguru import logger


class HTTPPool:
    """
    全局共享 HTTP 连接池（单例）

    - 自动管理 aiohttp.ClientSession 的生命周期
    - session 关闭后自动重建
    - 支持 async with 模式
    - 提供 get / post 便捷方法
    """

    def __init__(
        self,
        timeout: int = 15,
        connector_limit: int = 100,
        connector_limit_per_host: int = 30,
        dns_cache_ttl: int = 300,
    ) -> None:
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._connector_limit = connector_limit
        self._connector_limit_per_host = connector_limit_per_host
        self._dns_cache_ttl = dns_cache_ttl
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------
    # session 管理
    # ------------------------------------------------------------------

    async def get_session(self) -> aiohttp.ClientSession:
        """获取共享 session，若已关闭则自动重建。"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=self._connector_limit,
                limit_per_host=self._connector_limit_per_host,
                ttl_dns_cache=self._dns_cache_ttl,
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self._timeout,
            )
            logger.debug("HTTPPool: 已创建新的 ClientSession")
        return self._session

    async def close(self) -> None:
        """关闭 session，用于优雅退出。"""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            logger.debug("HTTPPool: ClientSession 已关闭")
        self._session = None

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "HTTPPool":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        await self.close()

    # ------------------------------------------------------------------
    # 便捷请求方法
    # ------------------------------------------------------------------

    async def get(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> aiohttp.ClientResponse:
        """
        发送 GET 请求，返回 ClientResponse 对象（由调用方决定如何消费）。
        调用方仍需使用 ``async with`` 来管理响应生命周期。
        """
        session = await self.get_session()
        kw: Dict[str, Any] = {}
        if headers:
            kw["headers"] = headers
        if params:
            kw["params"] = params
        if timeout is not None:
            kw["timeout"] = aiohttp.ClientTimeout(total=timeout)
        return await session.get(url, **kw)

    async def post(
        self,
        url: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> aiohttp.ClientResponse:
        """
        发送 POST 请求。支持 JSON body 和 form-data，二者互斥。
        返回 ClientResponse 对象。
        """
        session = await self.get_session()
        kw: Dict[str, Any] = {}
        if json is not None:
            kw["json"] = json
        if data is not None:
            kw["data"] = data
        if headers:
            kw["headers"] = headers
        if timeout is not None:
            kw["timeout"] = aiohttp.ClientTimeout(total=timeout)
        return await session.post(url, **kw)

    async def put(
        self,
        url: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> aiohttp.ClientResponse:
        """发送 PUT 请求。"""
        session = await self.get_session()
        kw: Dict[str, Any] = {}
        if json is not None:
            kw["json"] = json
        if headers:
            kw["headers"] = headers
        if timeout is not None:
            kw["timeout"] = aiohttp.ClientTimeout(total=timeout)
        return await session.put(url, **kw)

    async def request(
        self,
        method: str,
        url: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> aiohttp.ClientResponse:
        """通用请求方法。"""
        session = await self.get_session()
        kw: Dict[str, Any] = {}
        if json is not None:
            kw["json"] = json
        if data is not None:
            kw["data"] = data
        if headers:
            kw["headers"] = headers
        if params:
            kw["params"] = params
        if timeout is not None:
            kw["timeout"] = aiohttp.ClientTimeout(total=timeout)
        return await session.request(method, url, **kw)


# ------------------------------------------------------------------
# 全局单例
# ------------------------------------------------------------------
http_pool = HTTPPool()


async def close_http_pool() -> None:
    """优雅关闭全局连接池，适合在应用 shutdown 事件中调用。"""
    await http_pool.close()
