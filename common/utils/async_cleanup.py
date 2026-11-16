"""保护请求结束前的必要收尾，完成后再传播取消信号。"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from anyio import CancelScope
from loguru import logger

CleanupResult = TypeVar("CleanupResult")


async def complete_before_cancellation(
    cleanup: Coroutine[Any, Any, CleanupResult], *, operation: str,
) -> CleanupResult:
    """等待收尾完成，避免请求取消导致审计遗漏或会话提前关闭。

    Args:
        cleanup: 必须完成的收尾协程，不应包含新的主业务操作。
        operation: 操作及请求上下文，用于记录取消或收尾异常。
    Returns:
        未取消时返回协程结果；取消时等待同一任务结束后传播取消。
        收尾自身取消时传播取消；收尾失败且请求未取消时传播原异常，
        请求已取消时记录收尾异常并保留取消语义，不遗留后台任务。
    """
    task = asyncio.create_task(cleanup)
    cancellation = None
    # 首次取消仍需被观察；之后屏蔽 AnyIO 持续投递的取消，避免循环空转。
    # asyncio.Task.cancel() 不受 CancelScope 屏蔽，仍由循环等待同一收尾任务。
    with CancelScope() as cancel_scope:
        while True:
            try:
                result = await asyncio.shield(task)
                break
            except asyncio.CancelledError as exc:
                if task.cancelled():
                    raise
                if cancellation is None:
                    cancellation = exc
                    logger.warning("请求取消，等待必要收尾完成：operation={}", operation)
                cancel_scope.shield = True
            except Exception as exc:
                if cancellation is not None:
                    logger.opt(exception=exc).error("请求取消后的收尾失败：operation={}", operation)
                    raise cancellation from exc
                raise
    if cancellation is not None:
        raise cancellation
    return result
