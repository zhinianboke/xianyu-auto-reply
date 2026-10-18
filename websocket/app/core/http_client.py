"""WebSocket 服务使用的异步 HTTP 客户端。"""
from __future__ import annotations

from typing import Any
import aiohttp


class HTTPClient:
    """复用一个 ClientSession 发起外部 JSON POST 请求。"""
    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self._session

    async def post(self, url: str, headers: dict[str, str] | None = None,
                   json: dict[str, Any] | None = None, data: Any = None,
                   timeout: int | None = None, max_retries: int | None = None) -> Any:
        """发送 POST 请求并解析 JSON 响应。"""
        session = await self._get_session()
        retries = max_retries if max_retries is not None else 1
        request_timeout = aiohttp.ClientTimeout(total=timeout or 30)
        last_error: Exception | None = None
        for attempt in range(max(1, retries)):
            try:
                async with session.post(url, headers=headers, json=json, data=data, timeout=request_timeout) as response:
                    response.raise_for_status()
                    try:
                        return await response.json()
                    except (aiohttp.ContentTypeError, ValueError):
                        return {"text": await response.text()}
            except (aiohttp.ClientError, TimeoutError) as exc:
                last_error = exc
                if attempt + 1 < max(1, retries):
                    continue
        raise last_error or RuntimeError("HTTP 请求失败")

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None


_client: HTTPClient | None = None


def get_http_client() -> HTTPClient:
    """获取全局 HTTP 客户端。"""
    global _client
    if _client is None:
        _client = HTTPClient()
    return _client


async def close_http_client() -> None:
    """关闭全局 HTTP 客户端。"""
    if _client is not None:
        await _client.close()
