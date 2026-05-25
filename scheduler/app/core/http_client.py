"""
HTTP客户端模块

功能：
1. 封装aiohttp客户端
2. 实现连接池管理
3. 实现重试机制
4. 实现超时控制
5. 实现错误处理
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import aiohttp
from loguru import logger


class HTTPClient:
    """
    HTTP客户端
    
    提供统一的HTTP请求接口,支持:
    - 连接池管理
    - 自动重试(指数退避)
    - 超时控制
    - 错误处理
    """
    
    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        初始化HTTP客户端
        
        Args:
            timeout: 请求超时时间(秒)
            max_retries: 最大重试次数
            retry_delay: 初始重试延迟(秒),使用指数退避
        """
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建session"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,  # 最大连接数
                limit_per_host=30,  # 每个主机最大连接数
                ttl_dns_cache=300,  # DNS缓存时间
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self.timeout,
            )
        return self._session
    
    async def close(self):
        """关闭session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        发送HTTP请求(带重试)
        
        Args:
            method: HTTP方法
            url: 请求URL
            headers: 请求头
            json: JSON数据
            data: 表单数据
            params: URL参数
            
        Returns:
            响应数据
            
        Raises:
            aiohttp.ClientError: 请求失败
        """
        session = await self._get_session()
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json,
                    data=data,
                    params=params,
                ) as response:
                    # 检查HTTP状态码
                    if response.status >= 500:
                        # 服务器错误,可以重试
                        error_text = await response.text()
                        raise aiohttp.ClientError(
                            f"服务器错误 {response.status}: {error_text}"
                        )
                    
                    # 解析响应
                    try:
                        result = await response.json()
                    except Exception:
                        # 如果不是JSON,返回文本
                        text = await response.text()
                        result = {"text": text}
                    
                    # 检查业务状态码
                    if response.status >= 400:
                        logger.warning(
                            f"请求失败 {method} {url}: "
                            f"status={response.status}, result={result}"
                        )
                    
                    return result
                    
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
            ) as e:
                last_error = e
                
                # 判断是否应该重试
                if attempt < self.max_retries - 1:
                    # 计算退避延迟(指数退避: 1s, 2s, 4s)
                    delay = self.retry_delay * (2 ** attempt)
                    
                    logger.warning(
                        f"请求失败,{delay}秒后重试 "
                        f"(第{attempt + 1}/{self.max_retries}次): "
                        f"{method} {url}, 错误: {str(e)}"
                    )
                    
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"请求失败,已达最大重试次数: "
                        f"{method} {url}, 错误: {str(e)}"
                    )
        
        # 所有重试都失败
        raise last_error or aiohttp.ClientError("请求失败")
    
    async def post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """POST请求"""
        return await self.request("POST", url, headers=headers, json=json, data=data)
    
# 全局HTTP客户端实例
_http_client: Optional[HTTPClient] = None


def get_http_client() -> HTTPClient:
    """获取全局HTTP客户端实例"""
    global _http_client
    if _http_client is None:
        _http_client = HTTPClient()
    return _http_client


async def close_http_client():
    """关闭全局HTTP客户端"""
    global _http_client
    if _http_client:
        await _http_client.close()
        _http_client = None
