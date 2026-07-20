"""
Token 缓存写入服务。

功能：
1. 按 Token 缓存行、用户 ID、Device ID 条件写入续期 Token
2. 保持与定时续期任务一致的并发保护条件，避免覆盖其他流程已更新的缓存
3. 支持聊天 Token 基础缓存 upsert 和安全失效标记
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, update
from sqlalchemy.dialects.mysql import insert

from common.db.session import async_session_maker
from common.models.token_cache import TokenCache
from common.utils.time_utils import get_beijing_now_naive, random_token_cache_expiry


DEFAULT_DB_MAX_ATTEMPTS = 3
DEFAULT_DB_RETRY_DELAY_SECONDS = 0.5


@dataclass(frozen=True, slots=True)
class TokenRenewalCacheWriteResult:
    """Token 续期缓存写入结果。"""

    success: bool
    renew_expire_at: datetime | None = None
    ttl_hours: float = 0.0
    message: str = ""


@dataclass(frozen=True, slots=True)
class TokenCacheUpsertResult:
    """Token 基础缓存新增或更新结果。"""

    success: bool
    expire_at: datetime | None = None
    ttl_hours: float = 0.0
    message: str = ""


@dataclass(frozen=True, slots=True)
class TokenCacheInvalidationResult:
    """Token 缓存失效标记结果。"""

    success: bool
    changed: bool = False
    message: str = ""


async def mark_token_cache_expired(
    *,
    token_user_id: str,
    expired_at: datetime | None = None,
    expected_token: str | None = None,
    expected_device_id: str | None = None,
    invalidate_valid_cache: bool = False,
    max_attempts: int = DEFAULT_DB_MAX_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_DB_RETRY_DELAY_SECONDS,
) -> TokenCacheInvalidationResult:
    """安全标记 Token 缓存失效，避免删除数据或覆盖并发更新。

    Args:
        token_user_id: Token 缓存用户 ID。
        expired_at: 到期判断时间，默认当前北京时间。
        expected_token: 可选的当前失效 Token；传入后仅匹配该 Token。
        expected_device_id: 可选的当前设备 ID，与 expected_token 一起限制更新范围。
        invalidate_valid_cache: 是否连同尚未到期的缓存一起标记失效，适用于 Cookie 已整体更换。
        max_attempts: 数据库写入最大尝试次数。
        retry_delay_seconds: 相邻重试之间的等待秒数。
    Returns:
        操作成功时返回是否实际更新了缓存行。
    """
    clean_user_id = str(token_user_id or "").strip()
    if not clean_user_id:
        return TokenCacheInvalidationResult(False, message="Token缓存失效标记失败：用户ID为空")

    checked_at = expired_at or get_beijing_now_naive()
    attempts = max(1, int(max_attempts))
    clean_expected_token = str(expected_token or "").strip()
    clean_expected_device_id = str(expected_device_id or "").strip()
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            async with async_session_maker() as session:
                conditions = [TokenCache.user_id == clean_user_id]
                if clean_expected_token:
                    conditions.append(TokenCache.token == clean_expected_token)
                elif not invalidate_valid_cache:
                    conditions.append(TokenCache.expire_at <= checked_at)
                if clean_expected_device_id:
                    conditions.append(TokenCache.device_id == clean_expected_device_id)
                update_result = await session.execute(
                    update(TokenCache)
                    .where(*conditions)
                    .values(
                        expire_at=checked_at,
                        renew_expire_at=checked_at,
                        updated_at=checked_at,
                    )
                )
                await session.commit()
            break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                await asyncio.sleep(max(0.0, retry_delay_seconds))
    else:
        return TokenCacheInvalidationResult(
            False,
            message=f"Token缓存失效标记失败，已重试{attempts}次：{last_error}",
        )

    changed = bool(update_result.rowcount)
    return TokenCacheInvalidationResult(
        True,
        changed=changed,
        message=(
            "Token缓存已标记为失效"
            if changed
            else "Token缓存不存在、已失效或已被其他流程更新"
        ),
    )


async def upsert_token_cache(
    *,
    token_user_id: str,
    device_id: str,
    token: str,
    max_attempts: int = DEFAULT_DB_MAX_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_DB_RETRY_DELAY_SECONDS,
) -> TokenCacheUpsertResult:
    """按 Token 用户 ID 新增或更新基础缓存。

    Args:
        token_user_id: Token 缓存用户 ID，例如 ``chat_{myid}``。
        device_id: 当前 Token 使用的 Device ID。
        token: 新获取的 IM Token。
        max_attempts: 数据库写入最大尝试次数。
        retry_delay_seconds: 相邻重试之间的等待秒数。
    Returns:
        写入成功时返回基础缓存到期日；失败时返回具体中文原因。
    """
    clean_user_id = str(token_user_id or "").strip()
    clean_device_id = str(device_id or "").strip()
    clean_token = str(token or "").strip()
    if not clean_user_id:
        return TokenCacheUpsertResult(False, message="Token缓存写入失败：用户ID为空")
    if not clean_device_id:
        return TokenCacheUpsertResult(False, message="Token缓存写入失败：Device ID为空")
    if not clean_token:
        return TokenCacheUpsertResult(False, message="Token缓存写入失败：新Token为空")

    expire_at, ttl_hours = random_token_cache_expiry()
    attempts = max(1, int(max_attempts))
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            async with async_session_maker() as session:
                statement = insert(TokenCache).values(
                    user_id=clean_user_id,
                    token=clean_token,
                    device_id=clean_device_id,
                    expire_at=expire_at,
                )
                statement = statement.on_duplicate_key_update(
                    token=statement.inserted.token,
                    device_id=statement.inserted.device_id,
                    expire_at=statement.inserted.expire_at,
                    renew_expire_at=None,
                    updated_at=get_beijing_now_naive(),
                )
                await session.execute(statement)
                await session.commit()
            break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                await asyncio.sleep(max(0.0, retry_delay_seconds))
    else:
        return TokenCacheUpsertResult(
            False,
            message=f"Token缓存写入失败，已重试{attempts}次：{last_error}",
        )

    return TokenCacheUpsertResult(
        True,
        expire_at=expire_at,
        ttl_hours=ttl_hours,
        message=f"Token缓存写入成功，TTL={ttl_hours:.1f}小时",
    )


async def write_renewed_token_cache(
    *,
    cache_id: int,
    token_user_id: str,
    device_id: str,
    token: str,
    checked_at: datetime | None = None,
    max_attempts: int = DEFAULT_DB_MAX_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_DB_RETRY_DELAY_SECONDS,
) -> TokenRenewalCacheWriteResult:
    """条件写入续期 Token 缓存。

    Args:
        cache_id: ``xy_token_cache.id``。
        token_user_id: Token 缓存用户 ID。
        device_id: 当前缓存绑定的 Device ID。
        token: 新获取的 IM Token。
        checked_at: 判定原缓存已失效的时间，默认当前北京时间。
        max_attempts: 数据库写入最大尝试次数。
        retry_delay_seconds: 相邻重试之间的等待秒数。
    Returns:
        写入成功时返回续期到期日；失败时返回清晰中文原因。
    """
    if not str(token or "").strip():
        return TokenRenewalCacheWriteResult(False, message="Token缓存写入失败：新Token为空")

    renew_expire_at, ttl_hours = random_token_cache_expiry()
    checked_time = checked_at or get_beijing_now_naive()
    attempts = max(1, int(max_attempts))
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            async with async_session_maker() as session:
                update_result = await session.execute(
                    update(TokenCache)
                    .where(
                        TokenCache.id == cache_id,
                        TokenCache.user_id == token_user_id,
                        TokenCache.device_id == device_id,
                        TokenCache.expire_at <= checked_time,
                        or_(
                            TokenCache.renew_expire_at.is_(None),
                            TokenCache.renew_expire_at <= checked_time,
                        ),
                    )
                    .values(token=token, renew_expire_at=renew_expire_at)
                )
                if update_result.rowcount != 1:
                    await session.rollback()
                    return TokenRenewalCacheWriteResult(
                        False,
                        message="Token缓存已被其他流程更新，本次未写入",
                    )
                await session.commit()
            break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < attempts:
                await asyncio.sleep(max(0.0, retry_delay_seconds))
    else:
        return TokenRenewalCacheWriteResult(
            False,
            message=f"Token缓存写入失败，已重试{attempts}次：{last_error}",
        )

    return TokenRenewalCacheWriteResult(
        True,
        renew_expire_at=renew_expire_at,
        ttl_hours=ttl_hours,
        message=f"续期成功，TTL={ttl_hours:.1f}小时",
    )
