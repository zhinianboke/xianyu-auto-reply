"""认证限流：使用全局 Redis 池，对注册、验证码发送和登录失败原子计数。"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from common.db.redis_client import get_redis_client
from common.services.redis_rate_limit_service import check_sliding_window_limit

REGISTRATION_WINDOW_SECONDS = 24 * 60 * 60
REGISTRATION_IP_MAX_REQUESTS = 4
REGISTRATION_EMAIL_MAX_REQUESTS = 2
LOGIN_WINDOW_SECONDS = 10 * 60
LOGIN_IP_MAX_FAILURES = 10
LOGIN_IDENTITY_MAX_FAILURES = 10
LOGIN_CONSECUTIVE_MAX_FAILURES = 5
LOGIN_LOCK_HOURS = 3

# 登录先占位以避免并发绕过；成功清除失败记录，保留其他正在执行的请求。
LOGIN_BEGIN_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local window = tonumber(ARGV[2])
local member = 'p:' .. ARGV[1]
for i, key in ipairs(KEYS) do
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
    local limit = tonumber(i == 1 and ARGV[3] or ARGV[4])
    if not redis.call('ZSCORE', key, member) and redis.call('ZCARD', key) >= limit then
        return i
    end
end
for _, key in ipairs(KEYS) do
    redis.call('ZADD', key, 'NX', now, member)
    redis.call('PEXPIRE', key, window)
end
return 0
"""
LOGIN_FINISH_SCRIPT = """
local member = 'p:' .. ARGV[1]
local failed_member = 'f:' .. ARGV[1]
local clear_snapshot = nil
if ARGV[4] ~= '' then
    clear_snapshot = cjson.decode(ARGV[4])
end
local captured = {}
for i, key in ipairs(KEYS) do
    local score = redis.call('ZSCORE', key, member) or redis.call('ZSCORE', key, failed_member)
    redis.call('ZREM', key, member)
    if score and ARGV[2] == 'success' then
        local members = clear_snapshot and clear_snapshot[i] or redis.call('ZRANGE', key, 0, -1)
        for _, entry in ipairs(members) do
            if string.sub(entry, 1, 2) == 'f:' then redis.call('ZREM', key, entry) end
        end
        redis.call('ZREM', key, failed_member)
    elseif score then
        redis.call('ZADD', key, score, failed_member)
        redis.call('PEXPIRE', key, tonumber(ARGV[3]))
    end
    if ARGV[5] == 'snapshot' then
        local failures = {}
        local members = redis.call('ZRANGE', key, 0, -1)
        for _, entry in ipairs(members) do
            if string.sub(entry, 1, 2) == 'f:' then table.insert(failures, entry) end
        end
        table.insert(captured, failures)
    end
end
if ARGV[5] == 'snapshot' then
    return captured
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


@dataclass(frozen=True)
class LoginSuccessSnapshot:
    """成功提交前捕获的逐键失败成员，绑定原占位，避免清掉稍后发生的新失败。"""

    attempt: LoginAttempt
    failed_members: tuple[tuple[str, ...], ...]


def _identity_key(namespace: str, identity: str) -> str:
    """构造认证计数键；参数为命名空间和身份，返回 SHA256 哈希后的 Redis 键。"""
    digest = hashlib.sha256(
        identity.strip().casefold().encode('utf-8', errors='surrogatepass')
    ).hexdigest()
    return f"rate:auth:{namespace}:{digest}"


def _login_identity_keys(account: str | None, email: str | None = None) -> list[str]:
    """返回请求可识别身份的去重哈希键；参数缺失时不生成虚假身份额度。"""
    return list(dict.fromkeys(
        _identity_key('login:identity', identity)
        for identity in (account, email)
        if isinstance(identity, str) and identity.strip()
    ))


async def _reserve_login_attempt(attempt: LoginAttempt) -> LoginAttempt:
    """整组原子检查并占用缺失键；重试与身份扩展保留已占用成员的原始时间。"""
    client = await get_redis_client()
    blocked = int(await client.eval(
        LOGIN_BEGIN_SCRIPT, len(attempt.keys), *attempt.keys, attempt.request_id,
        LOGIN_WINDOW_SECONDS * 1000, LOGIN_IP_MAX_FAILURES, LOGIN_IDENTITY_MAX_FAILURES,
    ))
    if blocked:
        dimension = "当前 IP" if blocked == 1 else "该账号或邮箱"
        raise AuthRateLimitRejected(f"{dimension}登录失败次数过多，请10分钟后再试")
    return attempt


async def begin_login_attempt(ip: str | None, account: str | None, email: str | None = None) -> LoginAttempt:
    """查询用户前先占用IP和请求身份额度，数据库查找失败仍有可收尾的占位。"""
    keys = [_identity_key('login:ip', ip or 'unknown'), *_login_identity_keys(account, email)]
    return await _reserve_login_attempt(LoginAttempt(tuple(keys), uuid.uuid4().hex))


async def extend_login_attempt(attempt: LoginAttempt, account: str, email: str | None = None) -> LoginAttempt:
    """查到用户后以同一请求扩展用户名和绑定邮箱，不重复占用IP或已有身份。

    Args:
        attempt: 用户查询前的请求占位；调用方须在成功返回后才替换本地引用。
        account: 数据库中的用户名。
        email: 数据库中的绑定邮箱。
    Returns:
        共享请求编号的扩展占位；拒绝或Redis失败时原占位仍可按失败收尾。
    """
    keys = tuple(dict.fromkeys((*attempt.keys, *_login_identity_keys(account, email))))
    return await _reserve_login_attempt(LoginAttempt(keys, attempt.request_id))


async def finish_login_attempt(
    attempt: LoginAttempt, *, success: bool, prepare_success: bool = False,
    snapshot: LoginSuccessSnapshot | None = None,
) -> LoginSuccessSnapshot | None:
    """幂等收尾；成功只清除提交前快照内的失败，保留提交之后发生的新失败。

    Args:
        attempt: 本次登录的哈希键与请求编号。
        success: 提交前先传False持久化候选；数据库成功提交后传True清零。
        prepare_success: 仅False阶段启用，持有账号行锁时捕获有界失败成员快照。
        snapshot: True阶段传入原快照；省略时保留旧调用的全清失败记录行为。
    Returns:
        准备成功时返回逐键快照，否则返回None；Redis失败仍向入口传播。
    """
    if prepare_success and success:
        raise ValueError("登录成功快照必须在数据库提交前准备")
    if snapshot is not None and (not success or snapshot.attempt != attempt):
        raise ValueError("登录成功快照必须用于同一次登录的成功收尾")
    if snapshot is not None and len(snapshot.failed_members) != len(attempt.keys):
        raise ValueError("登录成功快照与登录身份数量不一致")
    client = await get_redis_client()
    captured = await client.eval(
        LOGIN_FINISH_SCRIPT, len(attempt.keys), *attempt.keys,
        attempt.request_id, 'success' if success else 'failure', LOGIN_WINDOW_SECONDS * 1000,
        json.dumps(snapshot.failed_members, separators=(',', ':')) if snapshot else '',
        'snapshot' if prepare_success else '',
    )
    if not prepare_success:
        return None
    if not isinstance(captured, (list, tuple)) or len(captured) != len(attempt.keys):
        raise ValueError("登录成功快照返回格式无效，请稍后重试")
    failures = []
    for group in captured:
        if not isinstance(group, (list, tuple)):
            raise TypeError("登录成功快照成员格式无效，请稍后重试")
        members = tuple(entry.decode('utf-8') if isinstance(entry, bytes) else entry for entry in group)
        if any(not isinstance(entry, str) or not entry.startswith('f:') for entry in members):
            raise ValueError("登录成功快照成员格式无效，请稍后重试")
        failures.append(members)
    return LoginSuccessSnapshot(attempt, tuple(failures))


async def check_registration_limit(ip: str | None, email: str | None = None) -> None:
    """注册尝试按24小时计数；参数非法时仍计IP，并计入入口可识别的邮箱。

    Args:
        ip: 公共方法校验后的客户端IP，未知对端使用统一未知来源键。
        email: 可识别的邮箱；缺失或非字符串时只计IP，不生成虚假邮箱键。
    Returns:
        无返回值；超限抛出中文业务错误，Redis失败继续向入口传播。
    """
    ip_result = await check_sliding_window_limit(
        'auth:register:ip', ip or 'unknown',
        window_seconds=REGISTRATION_WINDOW_SECONDS, max_requests=REGISTRATION_IP_MAX_REQUESTS,
    )
    email_identity = email.strip().casefold() if isinstance(email, str) else ''
    email_result = None
    if email_identity:
        # 即使IP超限也检查可识别邮箱，避免该维度漏掉本次拒绝尝试。
        email_result = await check_sliding_window_limit(
            'auth:register:email', email_identity,
            window_seconds=REGISTRATION_WINDOW_SECONDS, max_requests=REGISTRATION_EMAIL_MAX_REQUESTS,
        )
    if not ip_result.allowed:
        raise AuthRateLimitRejected(
            f"当前 IP 24小时内注册尝试次数已达{REGISTRATION_IP_MAX_REQUESTS}次，请稍后再试"
        )
    if email_result is not None and not email_result.allowed:
        raise AuthRateLimitRejected(
            f"该邮箱24小时内注册尝试次数已达{REGISTRATION_EMAIL_MAX_REQUESTS}次，请稍后再试"
        )


async def check_email_code_limit(ip: str | None, email: str | None, purpose: str) -> None:
    """验证码请求含参数拒绝按用途计数；没有可识别邮箱时仅计 IP，不补造邮箱。"""
    ip_result = await check_sliding_window_limit(
        f'auth:code:{purpose}:ip', ip or 'unknown', window_seconds=600, max_requests=5,
    )
    email_identity = email.strip().casefold() if isinstance(email, str) else ''
    email_result = None
    if email_identity:
        email_result = await check_sliding_window_limit(
            f'auth:code:{purpose}:email', email_identity, window_seconds=60, max_requests=1,
        )
    if not ip_result.allowed or (email_result is not None and not email_result.allowed):
        raise AuthRateLimitRejected("验证码发送过于频繁，请稍后再试")
