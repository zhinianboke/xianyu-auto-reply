"""
Redis健康连接池

功能：
1. 在连接出池和归还前检查 writer 与 transport 状态
2. 主动断开并重建已经失效的连接
3. 拦截 uvloop 已关闭 handler/transport 的失效连接异常
4. 避免在连接池锁内执行健康检查
"""
from __future__ import annotations

from typing import Any, Iterable

from loguru import logger
from redis.asyncio.connection import AbstractConnection, Connection, ConnectionPool
from redis.event import AsyncAfterConnectionReleasedEvent
from redis.exceptions import ConnectionError, TimeoutError as RedisTimeoutError

_CLOSED_TRANSPORT_ERROR_MARKERS = (
    "handler is closed",
    "transport closed",
    "closed=true",
    "event loop is closed",
)


def _is_writer_closing(writer: Any) -> bool:
    """
    判断 asyncio writer 是否正在关闭

    Args:
        writer: Redis连接持有的StreamWriter

    Returns:
        writer已关闭或无法访问时返回True
    """
    if writer is None:
        return True

    try:
        if writer.is_closing():
            return True
        transport = getattr(writer, "transport", None)
        if transport is None:
            return True
        return bool(transport.is_closing())
    except (AttributeError, OSError, RuntimeError):
        return True


def is_connection_transport_closed(connection: AbstractConnection) -> bool:
    """
    判断Redis连接的TCP transport是否已经失效

    Args:
        connection: redis-py异步连接对象

    Returns:
        连接未建立、writer关闭或transport关闭时返回True
    """
    return _is_writer_closing(getattr(connection, "_writer", None))


def _is_closed_transport_error(error: RuntimeError) -> bool:
    """
    判断运行时异常是否由uvloop已关闭transport导致

    Args:
        error: 发送命令时捕获的RuntimeError

    Returns:
        异常文本命中已知关闭状态标记时返回True
    """
    message = str(error).lower()
    return any(marker in message for marker in _CLOSED_TRANSPORT_ERROR_MARKERS)


async def _disconnect_connection(connection: AbstractConnection) -> None:
    """
    安全断开失效连接

    Args:
        connection: 需要断开并丢弃的Redis连接
    """
    try:
        await connection.disconnect(nowait=True)
    except Exception as exc:
        logger.warning(
            f"清理失效Redis连接失败: connection={connection!r}, "
            f"error_type={type(exc).__name__}, error={exc}"
        )
        if is_connection_transport_closed(connection):
            try:
                connection._reader = None
                connection._writer = None
            except Exception as reset_exc:
                logger.error(
                    f"重置失效Redis连接状态失败: connection={connection!r}, "
                    f"error_type={type(reset_exc).__name__}, error={reset_exc}"
                )


class HealthyRedisConnection(Connection):
    """
    发送命令前再次校验transport的Redis异步连接

    连接池出池检查后仍可能在并发场景中关闭，因此发送命令前必须再检查一次，
    避免uvloop抛出“handler is closed”后进入业务调用链。
    """

    async def send_packed_command(
        self,
        command: bytes | str | Iterable[bytes],
        check_health: bool = True,
    ) -> None:
        """
        发送Redis命令并在transport失效时先重建连接

        Args:
            command: 已打包或待打包的Redis命令
            check_health: 是否执行redis-py连接健康检查
        """
        if is_connection_transport_closed(self):
            await _disconnect_connection(self)
            await self.connect_check_health(check_health=False)

        try:
            await super().send_packed_command(command, check_health=check_health)
        except RuntimeError as exc:
            if not _is_closed_transport_error(exc):
                raise
            await _disconnect_connection(self)
            raise ConnectionError(
                "Redis连接transport已关闭，本次命令未发送"
            ) from exc


class HealthyRedisConnectionPool(ConnectionPool):
    """
    Redis健康异步连接池

    连接出池后、连接池锁释放后再执行健康检查；失效连接不会归还空闲池。
    """

    def __init__(
        self,
        connection_class: type[AbstractConnection] = HealthyRedisConnection,
        max_connections: int | None = None,
        **connection_kwargs: Any,
    ) -> None:
        """
        初始化健康连接池

        Args:
            connection_class: 连接实现类
            max_connections: 最大连接数
            connection_kwargs: redis-py连接参数
        """
        super().__init__(
            connection_class=connection_class,
            max_connections=max_connections,
            **connection_kwargs,
        )

    async def get_connection(
        self,
        command_name: str | None = None,
        *keys: Any,
        **options: Any,
    ) -> AbstractConnection:
        """
        从连接池获取健康连接

        连接池锁只用于取出连接和登记占用状态，PING、读取状态检查等操作均在
        锁释放后执行，避免健康检查阻塞其他任务。

        Args:
            command_name: redis-py兼容参数，当前版本不使用
            keys: redis-py兼容参数，当前版本不使用
            options: redis-py兼容参数，当前版本不使用

        Returns:
            已完成连接和transport健康检查的连接
        """
        async with self._lock:
            connection = self.get_available_connection()

        try:
            await self.ensure_connection(connection)
            return connection
        except BaseException:
            await self.discard_connection(connection)
            raise

    async def ensure_connection(self, connection: AbstractConnection) -> None:
        """
        确保连接可用且transport未关闭

        Args:
            connection: 从连接池取出的连接
        """
        if is_connection_transport_closed(connection):
            await _disconnect_connection(connection)

        await connection.connect()

        if is_connection_transport_closed(connection):
            await _disconnect_connection(connection)
            raise ConnectionError("Redis连接建立后transport仍处于关闭状态")

        try:
            if await connection.can_read_destructive():
                raise ConnectionError("Connection has data")
        except (ConnectionError, RedisTimeoutError, OSError, RuntimeError) as exc:
            await _disconnect_connection(connection)
            await connection.connect()

            if is_connection_transport_closed(connection):
                await _disconnect_connection(connection)
                raise ConnectionError(
                    "Redis连接重建后transport仍处于关闭状态"
                ) from exc

            if await connection.can_read_destructive():
                raise ConnectionError("Connection not ready") from exc

    async def release(self, connection: AbstractConnection) -> None:
        """
        归还连接前检查transport，失效连接直接断开丢弃

        Args:
            connection: 使用完毕后归还的连接
        """
        if is_connection_transport_closed(connection):
            await self.discard_connection(connection)
            return

        async with self._lock:
            if connection not in self._in_use_connections:
                logger.warning(f"归还未登记在连接池中的Redis连接: {connection!r}")
                return
            self._in_use_connections.remove(connection)
            self._available_connections.append(connection)

        await self._event_dispatcher.dispatch_async(
            AsyncAfterConnectionReleasedEvent(connection)
        )

    async def discard_connection(self, connection: AbstractConnection) -> None:
        """
        从连接池登记状态中移除并断开失效连接

        Args:
            connection: 需要丢弃的连接
        """
        async with self._lock:
            self._in_use_connections.discard(connection)
            if connection in self._available_connections:
                self._available_connections.remove(connection)
        await _disconnect_connection(connection)


__all__ = [
    "HealthyRedisConnection",
    "HealthyRedisConnectionPool",
    "is_connection_transport_closed",
]
