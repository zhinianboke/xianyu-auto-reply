"""
Redis客户端

功能：
1. 提供异步Redis连接
2. 提供分布式锁服务
3. 支持连接池管理
"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as redis
from loguru import logger

from common.core.config import get_settings

settings = get_settings()

# 全局Redis连接池
_redis_pool: Optional[redis.ConnectionPool] = None
_redis_client: Optional[redis.Redis] = None


async def get_redis_client() -> redis.Redis:
    """获取Redis客户端（单例模式）"""
    global _redis_pool, _redis_client
    
    if _redis_client is None:
        _redis_pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=50,
            decode_responses=True,
            socket_timeout=5,          # 读写超时 5 秒
            socket_connect_timeout=3,  # 连接超时 3 秒
            retry_on_timeout=True,     # 超时后自动重试一次
            protocol=2,                # 强制使用 RESP2，兼容 Redis 5.x 及以下版本
        )
        _redis_client = redis.Redis(connection_pool=_redis_pool)
        
        # 测试连接
        try:
            await _redis_client.ping()
            logger.info(f"Redis连接成功: {settings.redis_host}:{settings.redis_port}/{settings.redis_db}")
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            raise
    
    return _redis_client


async def close_redis_client():
    """关闭Redis连接"""
    global _redis_pool, _redis_client
    
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
    
    if _redis_pool:
        await _redis_pool.disconnect()
        _redis_pool = None
    
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
            start_time = asyncio.get_event_loop().time()
            while True:
                if await self._try_acquire(client):
                    return True
                
                # 检查超时
                elapsed = asyncio.get_event_loop().time() - start_time
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
            logger.debug(f"获取锁成功: {self.lock_key}")
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
                logger.debug(f"释放锁成功: {self.lock_key}")
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
                logger.debug(f"延长锁成功: {self.lock_key}, 延长{extend_time}秒")
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
        except Exception:
            pass
        
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
