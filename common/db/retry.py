"""
数据库连接重试工具

提供异步数据库操作的自动重试装饰器。
默认仅识别"连接断开类"异常进行重试；调用方可显式开启 MySQL
锁等待超时/死锁重试，业务异常（如完整性约束、语法错误）始终直接抛出。

典型场景：
- MySQL 服务网络抖动（WinError 64 / 10054 / 10053）
- 长时间空闲连接被网络层强制关闭（asyncmy OperationalError 2013）
- VPN/防火墙重置 TCP 连接

使用方式：
    from common.db.retry import with_db_retry

    class MyService:
        @with_db_retry(max_retries=3, initial_delay=1.0)
        async def write_record(self, payload):
            async with async_session_maker() as session:
                ...
                await session.commit()

注意事项：
- 默认仅重试连接错误，IntegrityError / ProgrammingError 等业务错误立即抛出
- 仅对幂等写入可按需开启 ``retry_on_lock_contention=True``
- 重试期间会自动等待（指数退避），调用方需考虑总耗时（默认最大约 7 秒）
- SQLAlchemy 的 pool_pre_ping=True 会在重试时自动剔除死连接，无需手动 dispose
"""
from __future__ import annotations

import asyncio
import functools
from typing import Any, Awaitable, Callable, TypeVar

from loguru import logger
from sqlalchemy.exc import (
    DBAPIError,
    DisconnectionError,
    InterfaceError,
    OperationalError,
)

T = TypeVar("T")

# 连接断开类错误的关键字（asyncmy / pymysql / SQLAlchemy 不同包装下错误文案不一致，需字符串兜底匹配）
_RETRYABLE_KEYWORDS: tuple[str, ...] = (
    "Lost connection",                    # MySQL 2013 - 查询过程中连接丢失
    "MySQL server has gone away",         # MySQL 2006 - 服务端主动关闭空闲连接
    "Server has gone away",               # 同上变体
    "Can't connect to MySQL",             # MySQL 2003 - 无法建立连接
    "Connection refused",                 # 服务未启动 / 端口不通
    "Connection reset",                   # TCP RST
    "Broken pipe",                        # 写入已关闭的连接
    "BrokenPipeError",                    # 同上 Python 异常名
    "Connection was killed",              # 服务端 KILL CONNECTION
    "WinError 64",                        # 指定的网络名不再可用（Windows 网络共享失效）
    "WinError 10054",                     # 远程主机强迫关闭了一个现有的连接
    "WinError 10053",                     # 您的主机中的软件中止了一个已建立的连接
    "WinError 10060",                     # 由于连接方在一段时间后没有正确答复...连接尝试失败
)

# MySQL 瞬时锁竞争错误码：
# - 1205：等待行锁/间隙锁超时
# - 1213：死锁，InnoDB 已回滚当前事务
_LOCK_CONTENTION_ERROR_CODES: frozenset[int] = frozenset({1205, 1213})
_LOCK_CONTENTION_KEYWORDS: tuple[str, ...] = (
    "Lock wait timeout exceeded",
    "Deadlock found when trying to get lock",
)


def is_db_disconnect_error(exc: BaseException) -> bool:
    """判断异常是否为数据库连接断开类错误（值得重试）

    判定顺序：
    1. SQLAlchemy 明确的 DisconnectionError / InterfaceError → 直接判定为可重试
    2. OperationalError / DBAPIError → 检查错误文案中的关键字
    3. 其他类型 → 兜底字符串匹配（asyncmy 偶尔抛出非 SQLAlchemy 包装的异常）

    Args:
        exc: 待判定的异常实例

    Returns:
        True 表示该异常是连接断开类，可重试；False 表示业务错误，不应重试
    """
    # 明确的连接错误类（无需检查文案）
    if isinstance(exc, (DisconnectionError, InterfaceError)):
        return True

    # SQLAlchemy 包装的数据库异常 → 检查文案
    if isinstance(exc, (OperationalError, DBAPIError)):
        msg = str(exc)
        return any(keyword in msg for keyword in _RETRYABLE_KEYWORDS)

    # 兜底：未被 SQLAlchemy 包装的原生异常（如 asyncmy 直接抛出）
    msg = str(exc)
    return any(keyword in msg for keyword in _RETRYABLE_KEYWORDS)


def is_db_lock_contention_error(exc: BaseException) -> bool:
    """判断异常是否为 MySQL 瞬时锁竞争错误。

    Args:
        exc: 待判定的异常实例

    Returns:
        True 表示属于锁等待超时或死锁，可按调用方策略重试
    """
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ())
    if args and isinstance(args[0], int) and args[0] in _LOCK_CONTENTION_ERROR_CODES:
        return True

    msg = str(exc)
    return any(keyword in msg for keyword in _LOCK_CONTENTION_KEYWORDS)


def with_db_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 8.0,
    backoff_factor: float = 2.0,
    retry_on_lock_contention: bool = False,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """异步数据库操作重试装饰器

    默认仅对"连接断开类"错误进行重试；显式开启后可重试锁等待超时/死锁。
    其他错误立即抛出（避免无效重试 IntegrityError 等）。

    重试间隔采用指数退避：
        attempt 1 失败后等待 initial_delay 秒
        attempt 2 失败后等待 initial_delay * backoff_factor 秒
        ...
        最大不超过 max_delay 秒

    Args:
        max_retries: 最大重试次数（不含首次执行）。默认 3，即首次 + 3 次重试 = 最多 4 次执行
        initial_delay: 首次重试前等待的秒数（默认 1.0 秒）
        max_delay: 单次等待时间的上限（默认 8.0 秒）
        backoff_factor: 每次失败后等待时间的放大倍数（默认 2.0）
        retry_on_lock_contention: 是否额外重试 MySQL 锁等待超时/死锁。
            默认 False；仅幂等或失败后明确未完成写入的操作应开启。

    Returns:
        装饰器函数

    Example:
        >>> @with_db_retry(max_retries=3, initial_delay=1.0)
        ... async def write_log(payload):
        ...     async with async_session_maker() as session:
        ...         session.add(...)
        ...         await session.commit()
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay
            last_exc: BaseException | None = None

            # 总执行次数 = 1 (首次) + max_retries (重试)
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except BaseException as exc:
                    last_exc = exc
                    is_disconnect_error = is_db_disconnect_error(exc)
                    is_lock_contention_error = (
                        retry_on_lock_contention
                        and is_db_lock_contention_error(exc)
                    )

                    # 业务错误（IntegrityError 等）立即抛出，不重试
                    if not (is_disconnect_error or is_lock_contention_error):
                        raise

                    # 已达到重试上限，抛出最后一次异常
                    if attempt >= max_retries:
                        logger.error(
                            f"数据库操作 {func.__qualname__} 已重试 {max_retries} 次仍失败，"
                            f"放弃执行: {exc}"
                        )
                        raise

                    # 记录重试并等待
                    retry_reason = (
                        "连接断开类错误"
                        if is_disconnect_error
                        else "锁竞争类错误"
                    )
                    logger.warning(
                        f"数据库操作 {func.__qualname__} 第 {attempt + 1} 次执行失败"
                        f"（{retry_reason}），{delay:.1f} 秒后重试: {exc}"
                    )
                    await asyncio.sleep(delay)
                    # 指数退避，但不超过 max_delay
                    delay = min(delay * backoff_factor, max_delay)

            # 理论上不会到达这里（要么 return，要么 raise）
            assert last_exc is not None, "重试循环异常退出但 last_exc 为空"
            raise last_exc

        return wrapper

    return decorator


__all__ = [
    "is_db_disconnect_error",
    "is_db_lock_contention_error",
    "with_db_retry",
]
