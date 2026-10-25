"""使用全局 Redis 连接池执行原子滑动窗口限流。"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from common.db.redis_client import get_redis_client

SLIDING_WINDOW_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
-- 同一个请求因连接重试再次执行时，保留第一次放行结果，不重复计数。
if redis.call('ZSCORE', KEYS[1], ARGV[3]) then
    return {1, math.max(0, limit - count), 0}
end
if count >= limit then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    return {0, 0, math.max(1, tonumber(oldest[2]) + window - now)}
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], window)
return {1, limit - count - 1, 0}
"""


@dataclass(frozen=True)
class RateLimitResult:
    """记录本次请求是否放行、剩余额度和建议等待秒数。"""

    allowed: bool
    remaining: int
    retry_after: int


async def check_sliding_window_limit(
    namespace: str, identifier: str, *, window_seconds: int, max_requests: int,
) -> RateLimitResult:
    """按业务命名空间和标识限流；Redis 不可用时抛出异常，调用方必须明确拒绝请求。

    Args:
        namespace: Redis 限流键业务前缀。
        identifier: IP、账号等限流标识，写入 Redis 前统一哈希。
        window_seconds: 滑动窗口秒数。
        max_requests: 同一窗口允许的最大请求数。
    Returns:
        放行结果、剩余额度和拒绝时的重试等待秒数。
    """
    if window_seconds <= 0 or max_requests <= 0:
        raise ValueError("限流窗口和请求上限必须大于零")
    identity_hash = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    key = f"rate:{namespace}:{identity_hash}"
    client = await get_redis_client()
    result = await client.eval(
        SLIDING_WINDOW_SCRIPT, 1, key,
        window_seconds * 1000, max_requests, uuid.uuid4().hex,
    )
    return RateLimitResult(
        allowed=bool(int(result[0])), remaining=int(result[1]),
        retry_after=(int(result[2]) + 999) // 1000,
    )
