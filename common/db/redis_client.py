"""
Redis客户端

功能：
1. 提供异步Redis连接
2. 提供分布式锁服务
3. 支持连接池管理
"""
from __future__ import annotations

import asyncio
import socket
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialWithJitterBackoff
from loguru import logger

from common.core.config import get_settings
from common.db.redis_pool import HealthyRedisConnectionPool

settings = get_settings()

# 全局Redis连接池
redis_pool: Optional[HealthyRedisConnectionPool] = None
redis_client: Optional[redis.Redis] = None
_redis_init_lock = asyncio.Lock()


def _create_redis_pool() -> HealthyRedisConnectionPool:
    """
    创建全局Redis健康连接池

    Returns:
        使用统一重试策略和超时配置构建的连接池
    """
    retry = Retry(
        ExponentialWithJitterBackoff(base=1, cap=10),
        retries=3,
    )
    socket_keepalive_options = None
    if settings.redis_socket_keepalive:
        socket_keepalive_options = {}
        if hasattr(socket, "TCP_KEEPIDLE"):
            socket_keepalive_options[socket.TCP_KEEPIDLE] = (
                settings.redis_socket_keepalive_idle
            )
        if hasattr(socket, "TCP_KEEPINTVL"):
            socket_keepalive_options[socket.TCP_KEEPINTVL] = (
                settings.redis_socket_keepalive_interval
            )
        if hasattr(socket, "TCP_KEEPCNT"):
            socket_keepalive_options[socket.TCP_KEEPCNT] = (
                settings.redis_socket_keepalive_count
            )

    return HealthyRedisConnectionPool.from_url(
        settings.redis_url,
        max_connections=settings.redis_pool_size,
        decode_responses=True,
        socket_timeout=settings.redis_socket_timeout,
        socket_connect_timeout=settings.redis_socket_connect_timeout,
        socket_keepalive=settings.redis_socket_keepalive,
        socket_keepalive_options=socket_keepalive_options,
        health_check_interval=settings.redis_health_check_interval,
        retry=retry,
        protocol=settings.redis_protocol,
    )


async def _close_redis_resources(
    client: Optional[redis.Redis],
    pool: Optional[HealthyRedisConnectionPool],
) -> None:
    """
    按客户端、连接池顺序释放Redis资源

    Args:
        client: 待释放的Redis客户端
        pool: 待释放的Redis连接池
    """
    if client is not None:
        try:
            await client.aclose(close_connection_pool=False)
        except Exception as exc:
            logger.warning(
                f"释放Redis客户端失败: error_type={type(exc).__name__}, error={exc}"
            )

    if pool is not None:
        try:
            await pool.aclose()
        except Exception as exc:
            logger.warning(
                f"断开Redis连接池失败: error_type={type(exc).__name__}, error={exc}"
            )


async def initialize_redis_client() -> redis.Redis:
    """
    初始化Redis客户端并执行PING检查

    首次连接失败时按指数退避重试，最终失败会抛出异常并记录完整堆栈。

    Returns:
        已完成PING检查的全局Redis客户端
    """
    global redis_pool, redis_client

    async with _redis_init_lock:
        if redis_client is not None:
            return redis_client

        max_retries = settings.redis_startup_max_retries
        for attempt in range(max_retries + 1):
            pool: Optional[HealthyRedisConnectionPool] = None
            client: Optional[redis.Redis] = None
            try:
                pool = _create_redis_pool()
                client = redis.Redis(connection_pool=pool)
                await client.ping()

                redis_pool = pool
                redis_client = client
                logger.info(
                    "Redis连接成功: "
                    f"{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
                )
                return client
            except Exception as exc:
                await _close_redis_resources(client, pool)
                if attempt >= max_retries:
                    logger.exception(
                        "Redis初始化失败，已达到最大重试次数: "
                        f"attempt={attempt + 1}/{max_retries + 1}, "
                        f"error_type={type(exc).__name__}, error={exc}"
                    )
                    raise

                delay = min(
                    settings.redis_startup_retry_cap_delay,
                    settings.redis_startup_retry_base_delay * (2 ** attempt),
                )
                logger.warning(
                    "Redis初始化失败，准备重试: "
                    f"attempt={attempt + 1}/{max_retries + 1}, "
                    f"retry_after={delay:.2f}s, "
                    f"error_type={type(exc).__name__}, error={exc}"
                )
                await asyncio.sleep(delay)

        raise RuntimeError("Redis客户端初始化失败")


async def get_redis_client() -> redis.Redis:
    """
    获取全局Redis客户端

    Returns:
        已完成初始化的Redis客户端
    """
    return await initialize_redis_client()


async def close_redis_client() -> None:
    """关闭全局Redis客户端并断开整个连接池"""
    global redis_pool, redis_client

    client = redis_client
    pool = redis_pool
    redis_client = None
    redis_pool = None

    await _close_redis_resources(client, pool)
    logger.info("Redis连接已关闭")


class DistributedLock:
    """
    Redis分布式锁
    
    使用Redis的SETNX实现分布式锁，支持自动续期和超时释放
    """
    
    # 锁的默认过期时间（秒）
    DEFAULT_EXPIRE = 60
    
    # 锁的前缀
    LOCK_PREFIX = "lock:delivery:"
    
    def __init__(self, lock_name: str, expire: int = DEFAULT_EXPIRE):
        """
        初始化分布式锁
        
        Args:
            lock_name: 锁名称（如订单号）
            expire: 锁过期时间（秒），默认60秒
        """
        self.lock_name = lock_name
        self.lock_key = f"{self.LOCK_PREFIX}{lock_name}"
        self.expire = expire
        self.lock_value = str(uuid.uuid4())  # 唯一标识，用于安全释放
        self._locked = False
    
    async def acquire(self, blocking: bool = True, timeout: float = 10.0) -> bool:
        """
        获取锁
        
        Args:
            blocking: 是否阻塞等待
            timeout: 阻塞等待超时时间（秒）
            
        Returns:
            是否成功获取锁
        """
        client = await get_redis_client()
        
        if blocking:
            # 阻塞模式：循环尝试获取锁
            start_time = asyncio.get_running_loop().time()
            while True:
                if await self._try_acquire(client):
                    return True
                
                # 检查超时
                elapsed = asyncio.get_running_loop().time() - start_time
                if elapsed >= timeout:
                    logger.warning(f"获取锁超时: {self.lock_key}, 等待时间: {elapsed:.2f}s")
                    return False
                
                # 短暂等待后重试
                await asyncio.sleep(0.1)
        else:
            # 非阻塞模式：尝试一次
            return await self._try_acquire(client)
    
    async def _try_acquire(self, client: redis.Redis) -> bool:
        """尝试获取锁"""
        # 使用SET NX EX原子操作
        result = await client.set(
            self.lock_key,
            self.lock_value,
            nx=True,  # 只在key不存在时设置
            ex=self.expire,  # 过期时间
        )
        
        if result:
            self._locked = True
            logger.info(f"获取Redis分布式锁成功: key={self.lock_key}")
            return True
        
        return False
    
    async def release(self) -> bool:
        """
        释放锁
        
        使用Lua脚本确保只释放自己持有的锁
        
        Returns:
            是否成功释放
        """
        if not self._locked:
            return True
        
        client = await get_redis_client()
        
        # Lua脚本：只有锁的值匹配时才删除
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        
        try:
            result = await client.eval(lua_script, 1, self.lock_key, self.lock_value)
            self._locked = False
            
            if result:
                logger.info(f"释放Redis分布式锁成功: key={self.lock_key}")
                return True
            else:
                logger.warning(f"释放锁失败（锁已被其他进程持有或已过期）: {self.lock_key}")
                return False
        except Exception as e:
            logger.error(f"释放锁异常: {self.lock_key}, error={e}")
            return False
    
    async def extend(self, additional_time: int = None) -> bool:
        """
        延长锁的过期时间
        
        Args:
            additional_time: 额外时间（秒），默认使用初始过期时间
            
        Returns:
            是否成功延长
        """
        if not self._locked:
            return False
        
        client = await get_redis_client()
        extend_time = additional_time or self.expire
        
        # Lua脚本：只有锁的值匹配时才延长
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        
        try:
            result = await client.eval(lua_script, 1, self.lock_key, self.lock_value, extend_time)
            if result:
                logger.info(
                    f"延长Redis分布式锁成功: key={self.lock_key}, "
                    f"extend_seconds={extend_time}"
                )
                return True
            else:
                logger.warning(f"延长锁失败: {self.lock_key}")
                return False
        except Exception as e:
            logger.error(f"延长锁异常: {self.lock_key}, error={e}")
            return False
    
    @property
    def is_locked(self) -> bool:
        """是否持有锁"""
        return self._locked


@asynccontextmanager
async def distributed_lock(lock_name: str, expire: int = 60, blocking: bool = True, timeout: float = 10.0):
    """
    分布式锁上下文管理器
    
    用法：
        async with distributed_lock("order_123") as lock:
            if lock.is_locked:
                # 执行需要加锁的操作
                pass
    
    Args:
        lock_name: 锁名称
        expire: 锁过期时间（秒）
        blocking: 是否阻塞等待
        timeout: 阻塞等待超时时间（秒）
    """
    lock = DistributedLock(lock_name, expire)
    try:
        await lock.acquire(blocking=blocking, timeout=timeout)
        yield lock
    finally:
        await lock.release()


class LockResult:
    """
    分布式锁获取结果
    
    用于区分三种情况：
    1. 获取成功 - lock不为None，is_locked_by_other=False
    2. 锁被其他进程持有 - lock为None，is_locked_by_other=True
    3. Redis连接异常 - lock为None，is_locked_by_other=False，has_error=True
    """
    def __init__(self, lock: Optional[DistributedLock] = None, is_locked_by_other: bool = False, has_error: bool = False):
        self.lock = lock
        self.is_locked_by_other = is_locked_by_other
        self.has_error = has_error
    
    @property
    def success(self) -> bool:
        """是否成功获取锁"""
        return self.lock is not None and self.lock.is_locked


async def try_acquire_delivery_lock(order_no: str, expire: int = 120, holder_info: str = "", wait_timeout: float = 5.0) -> LockResult:
    """
    尝试获取发货锁（支持等待）
    
    用于自动发货和定时补发货的并发控制
    
    Args:
        order_no: 订单号
        expire: 锁过期时间（秒），默认120秒
        holder_info: 锁持有者信息（如cookie_id），用于调试
        wait_timeout: 等待超时时间（秒），默认5秒，0表示不等待
        
    Returns:
        LockResult对象，包含：
        - lock: 锁对象（成功时）或None
        - is_locked_by_other: 锁是否被其他进程持有
        - has_error: 是否发生Redis连接异常
    """
    try:
        # 如果有holder_info，将其作为锁值的一部分
        lock = DistributedLock(f"order:{order_no}", expire)
        if holder_info:
            lock.lock_value = f"{holder_info}:{lock.lock_value}"
        
        # 先尝试非阻塞获取
        if await lock.acquire(blocking=False):
            return LockResult(lock=lock)
        
        # 非阻塞获取失败，查询当前锁持有者信息
        try:
            client = await get_redis_client()
            current_holder = await client.get(lock.lock_key)
            ttl = await client.ttl(lock.lock_key)
            logger.warning(f"锁被占用，等待中: key={lock.lock_key}, 持有者={current_holder}, 剩余TTL={ttl}秒")
        except Exception as exc:
            logger.warning(
                f"查询Redis锁持有者信息失败: key={lock.lock_key}, "
                f"error_type={type(exc).__name__}, error={exc}"
            )
        
        # 如果配置了等待时间，继续阻塞等待
        if wait_timeout > 0:
            if await lock.acquire(blocking=True, timeout=wait_timeout):
                return LockResult(lock=lock)
        
        return LockResult(is_locked_by_other=True)
    except Exception as e:
        # Redis连接失败时记录警告
        logger.warning(f"Redis分布式锁获取异常（将降级为本地锁）: {e}")
        return LockResult(has_error=True)


async def release_delivery_lock(lock_result) -> bool:
    """
    释放发货锁
    
    Args:
        lock_result: LockResult对象或DistributedLock对象（兼容旧代码）
        
    Returns:
        是否成功释放
    """
    # 兼容处理：支持直接传入lock对象或LockResult对象
    lock = None
    if isinstance(lock_result, LockResult):
        lock = lock_result.lock
    elif isinstance(lock_result, DistributedLock):
        lock = lock_result
    
    if lock:
        try:
            return await lock.release()
        except Exception as e:
            logger.warning(f"Redis分布式锁释放异常: {e}")
            return False
    return True
