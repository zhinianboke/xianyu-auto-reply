"""
账号级 Token 请求分布式锁。

功能：
1. 使用 Redis 保证同一闲鱼账号同时只有一个 Token 获取流程
2. 持锁期间定时续期，覆盖远程接口重试和滑块处理等长耗时操作
3. Redis 不可用时降级为无锁并发调用，避免阻断 Token 获取
"""
from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from loguru import logger

from common.db.redis_client import DistributedLock


TOKEN_REQUEST_LOCK_EXPIRE_SECONDS = 600
TOKEN_REQUEST_LOCK_EXTEND_INTERVAL_SECONDS = 120
TOKEN_REQUEST_LOCK_WAIT_TIMEOUT_SECONDS = 900.0


class TokenRequestLockError(RuntimeError):
    """Token 请求锁不可用或等待超时。"""


class _TokenRequestDistributedLock(DistributedLock):
    """使用独立 Redis key 前缀的 Token 请求锁。"""

    LOCK_PREFIX = "lock:token_request:"


def _build_token_request_lock_name(account_identifier: str) -> str:
    """构造不暴露账号明文且长度固定的 Redis 锁名称。

    Args:
        account_identifier: 闲鱼账号唯一标识，优先使用 unb/myid。
    Returns:
        可安全用于 Redis key 的锁名称。
    """
    clean_identifier = str(account_identifier or "").strip()
    if not clean_identifier:
        raise TokenRequestLockError("Token请求加锁失败：账号标识为空")
    return hashlib.sha256(clean_identifier.encode("utf-8")).hexdigest()


async def _extend_token_request_lock(
    lock: DistributedLock,
    account_identifier: str,
) -> None:
    """持锁期间定时续期；Redis 异常时让当前业务无锁继续。"""
    while True:
        await asyncio.sleep(TOKEN_REQUEST_LOCK_EXTEND_INTERVAL_SECONDS)
        try:
            if await lock.extend(TOKEN_REQUEST_LOCK_EXPIRE_SECONDS):
                continue
            logger.warning(
                f"【{account_identifier}】Token请求Redis锁续期失败，"
                "当前Token流程降级为无锁继续执行"
            )
        except Exception as exc:
            logger.warning(
                f"【{account_identifier}】Token请求Redis锁续期异常: "
                f"{type(exc).__name__}: {exc}，当前Token流程降级为无锁继续执行"
            )
        return


@asynccontextmanager
async def token_request_lock(
    account_identifier: str,
    *,
    wait_timeout: float = TOKEN_REQUEST_LOCK_WAIT_TIMEOUT_SECONDS,
) -> AsyncIterator[None]:
    """获取账号级 Token 请求 Redis 锁。

    Args:
        account_identifier: 闲鱼账号唯一标识，优先使用 unb/myid。
        wait_timeout: 等待其他 Token 流程完成的最大秒数。
    Yields:
        成功持锁或 Redis 异常降级后，进入 Token 缓存复查与请求流程。
    Raises:
        TokenRequestLockError: Redis 正常但等待其他持锁流程超时时抛出。
    """
    clean_identifier = str(account_identifier or "").strip()
    lock_name = _build_token_request_lock_name(clean_identifier)
    lock = _TokenRequestDistributedLock(
        lock_name,
        expire=TOKEN_REQUEST_LOCK_EXPIRE_SECONDS,
    )
    try:
        acquired = await lock.acquire(blocking=True, timeout=max(0.0, wait_timeout))
    except Exception as exc:
        logger.warning(
            f"【{clean_identifier}】Token请求Redis锁不可用: "
            f"{type(exc).__name__}: {exc}，降级为无锁并发调用"
        )
        yield
        return
    if not acquired:
        raise TokenRequestLockError(
            f"同账号已有Token请求正在执行，等待{wait_timeout:.0f}秒后仍未完成"
        )

    extend_task = asyncio.create_task(
        _extend_token_request_lock(
            lock,
            clean_identifier,
        )
    )
    try:
        yield
    finally:
        extend_task.cancel()
        with suppress(asyncio.CancelledError):
            await extend_task
        try:
            if not await lock.release():
                logger.warning(f"【{clean_identifier}】Token请求Redis锁释放失败")
        except Exception as exc:
            logger.warning(
                f"【{clean_identifier}】Token请求Redis锁释放异常: "
                f"{type(exc).__name__}: {exc}"
            )
