"""
Future管理器模块

功能:
1. 统一管理异步Future的创建、解析和超时清理
2. 防止未响应的Future导致内存泄漏
"""

import asyncio
import time
from typing import Dict, Optional
from loguru import logger


class FutureInfo:
    """Future的元信息"""
    __slots__ = ('future', 'created_at', 'timeout', 'key')

    def __init__(self, future: asyncio.Future, key: str, timeout: float):
        self.future = future
        self.key = key
        self.timeout = timeout
        self.created_at = time.time()

    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.timeout


class FutureManager:
    """
    Future管理器，跟踪所有pending的Future并自动清理超时项。

    使用示例::

        mgr = FutureManager()
        await mgr.start()

        fut = mgr.create_future("req-123", timeout=30)
        # ... 发送请求 ...
        result = await fut  # 等待响应

        # 当响应到达时:
        mgr.resolve_future("req-123", response_data)

        await mgr.stop()
    """

    def __init__(self, name: str = "default", cleanup_interval: float = 60.0):
        """
        Args:
            name: 管理器名称（用于日志标识）
            cleanup_interval: 清理循环间隔（秒），默认60秒
        """
        self.name = name
        self.cleanup_interval = cleanup_interval
        self._futures: Dict[str, FutureInfo] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """启动清理循环"""
        if self._cleanup_task is not None:
            return
        self._cleanup_task = asyncio.ensure_future(self._cleanup_loop())
        logger.debug(f"FutureManager: 清理循环已启动")

    async def stop(self):
        """停止清理循环"""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        # 取消所有待处理的future
        for info in list(self._futures.values()):
            if not info.future.done():
                info.future.cancel()
        self._futures.clear()
        logger.debug(f"FutureManager: 已停止并清理所有futures")

    def create_future(self, key: str, timeout: float = 30.0) -> asyncio.Future:
        """
        创建一个新的Future并注册到管理器。

        Args:
            key: Future的唯一标识
            timeout: 超时时间（秒），默认30秒

        Returns:
            新创建的Future对象

        Raises:
            RuntimeError: 如果没有运行中的事件循环
        """
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        # 如果已有同key的future，先取消旧的
        old = self._futures.pop(key, None)
        if old is not None and not old.future.done():
            old.future.cancel()
            logger.debug(f"FutureManager: 替换未完成的future: {key}")

        self._futures[key] = FutureInfo(future, key, timeout)
        return future

    def resolve_future(self, key: str, result) -> bool:
        """
        解析指定key的Future。

        Args:
            key: Future的唯一标识
            result: 要设置的结果

        Returns:
            True如果成功设置结果，False如果Future不存在或已完成
        """
        info = self._futures.pop(key, None)
        if info is None:
            return False
        if info.future.done():
            return False
        info.future.set_result(result)
        return True

    def cancel_future(self, key: str) -> bool:
        """
        取消指定key的Future。

        Args:
            key: Future的唯一标识

        Returns:
            True如果成功取消，False如果Future不存在或已完成
        """
        info = self._futures.pop(key, None)
        if info is None:
            return False
        if info.future.done():
            return False
        info.future.cancel()
        return True

    @property
    def pending_count(self) -> int:
        """当前pending的Future数量"""
        return len(self._futures)

    async def _cleanup_loop(self):
        """定期清理超时的Future，防止内存泄漏"""
        try:
            while True:
                await asyncio.sleep(self.cleanup_interval)
                now = time.time()
                expired_keys = [
                    key for key, info in self._futures.items()
                    if info.is_expired
                ]
                for key in expired_keys:
                    info = self._futures.pop(key, None)
                    if info is not None and not info.future.done():
                        info.future.cancel()
                        logger.debug(
                            f"FutureManager: 清理超时future: {key} "
                            f"(超时 {info.timeout}s)"
                        )
                if expired_keys:
                    logger.info(
                        f"FutureManager: 清理超时futures: "
                        f"{len(expired_keys)}个，剩余: {len(self._futures)}个"
                    )
        except asyncio.CancelledError:
            logger.debug(f"FutureManager: 清理循环已取消")
        except Exception as e:
            logger.error(f"FutureManager: 清理循环异常: {e}")
