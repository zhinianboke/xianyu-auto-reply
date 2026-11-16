"""认证限流：使用全局 Redis 池，对注册、验证码发送和登录失败原子计数。"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from common.db.redis_client import get_redis_client
from common.services.redis_rate_limit_service import check_sliding_window_limit

# 登录先占位以避免并发绕过；成功清除失败记录，保留其他正在执行的请求。
LOGIN_BEGIN_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local member = 'p:' .. ARGV[1]
if redis.call('ZSCORE', KEYS[1], member) then return 0 end
for i, key in ipairs(KEYS) do
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now - 600000)
    local limit = i == 1 and 20 or 10
    if redis.call('ZCARD', key) >= limit then return i end
end
for _, key in ipairs(KEYS) do
    redis.call('ZADD', key, now, member)
    redis.call('PEXPIRE', key, 600000)
end
return 0
"""
LOGIN_FINISH_SCRIPT = """
local member = 'p:' .. ARGV[1]
for _, key in ipairs(KEYS) do
    local score = redis.call('ZSCORE', key, member)
    redis.call('ZREM', key, member)
    if score and ARGV[2] == 'success' then
        local members = redis.call('ZRANGE', key, 0, -1)
        for _, entry in ipairs(members) do
            if string.sub(entry, 1, 2) == 'f:' then redis.call('ZREM', key, entry) end
        end
    elseif score then
        redis.call('ZADD', key, score, 'f:' .. ARGV[1])
        redis.call('PEXPIRE', key, 600000)
    end
end
return 1
"""


class AuthRateLimitRejected(ValueError):
    """认证频率超过限制，统一返回业务码 42901。"""

    code = 42901


@dataclass(frozen=True)
class LoginAttempt:
    """一次登录占位的哈希键与唯一标识，不在 Redis 键中存储原始身份。"""

    keys: tuple[str, ...]
    request_id: str


def _identity_key(namespace: str, identity: str) -> str:
    """构造认证计数键；参数为命名空间和身份，返回 SHA256 哈希后的 Redis 键。"""
    digest = hashlib.sha256(identity.strip().casefold().encode('utf-8')).hexdigest()
    return f"rate:auth:{namespace}:{digest}"


async def begin_login_attempt(ip: str | None, account: str, email: str | None = None) -> LoginAttempt:
    """检查并占用 IP/账号/绑定邮箱额度；超限抛出业务错误，Redis 异常由入口处理。"""
    keys = [_identity_key('login:ip', ip or 'unknown'), _identity_key('login:identity', account)]
    if email:
        keys.append(_identity_key('login:identity', email))
    attempt = LoginAttempt(tuple(dict.fromkeys(keys)), uuid.uuid4().hex)
    client = await get_redis_client()
    blocked = int(await client.eval(LOGIN_BEGIN_SCRIPT, len(attempt.keys), *attempt.keys, attempt.request_id))
    if blocked:
        dimension = "当前 IP" if blocked == 1 else "该账号或邮箱"
        raise AuthRateLimitRejected(f"{dimension}登录失败次数过多，请10分钟后再试")
    return attempt


async def finish_login_attempt(attempt: LoginAttempt, *, success: bool) -> None:
    """结束本次登录占位；失败保留计数，成功清除对应维度的失败计数。"""
    client = await get_redis_client()
    await client.eval(
        LOGIN_FINISH_SCRIPT, len(attempt.keys), *attempt.keys,
        attempt.request_id, 'success' if success else 'failure',
    )


async def check_registration_limit(ip: str | None, email: str) -> None:
    """注册提交每次尝试都计数：同 IP 10 分钟 5 次、同邮箱 24 小时 1 次。"""
    ip_result = await check_sliding_window_limit(
        'auth:register:ip', ip or 'unknown', window_seconds=600, max_requests=5,
    )
    email_result = await check_sliding_window_limit(
        'auth:register:email', email.strip().casefold(), window_seconds=86400, max_requests=1,
    )
    if not ip_result.allowed:
        raise AuthRateLimitRejected("当前 IP 注册次数过多，请10分钟后再试")
    if not email_result.allowed:
        raise AuthRateLimitRejected("该邮箱24小时内已尝试注册，请稍后再试")


async def check_email_code_limit(ip: str | None, email: str, purpose: str) -> None:
    """验证码发送（含拒绝）按用途限制 IP 10 分钟 5 次、邮箱每分钟 1 次。"""
    ip_result = await check_sliding_window_limit(
        f'auth:code:{purpose}:ip', ip or 'unknown', window_seconds=600, max_requests=5,
    )
    email_result = await check_sliding_window_limit(
        f'auth:code:{purpose}:email', email.strip().casefold(), window_seconds=60, max_requests=1,
    )
    if not ip_result.allowed or not email_result.allowed:
        raise AuthRateLimitRejected("验证码发送过于频繁，请稍后再试")
