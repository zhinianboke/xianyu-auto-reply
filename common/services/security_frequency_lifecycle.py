"""安全频率检查生命周期：轻量轮询持久化下次执行，停止时排空执行和审计。"""
from __future__ import annotations

import asyncio

from common.services.audit_writer import report_safely
from common.services.security_frequency_service import security_frequency_service
from common.utils.async_cleanup import complete_before_cancellation


async def run_security_frequency(stop: asyncio.Event) -> None:
    """由应用生命周期启动；每20秒到期一次，未到期或其他实例占用不追加日志。"""
    while not stop.is_set():
        try:
            await security_frequency_service.execute()
        except Exception as exc:
            report_safely(f'自动安全检查失败 exception_type={type(exc).__name__} exception={exc}', exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=1)
        except TimeoutError:
            continue


async def stop_security_frequency(stop: asyncio.Event, worker: asyncio.Task) -> None:
    """关闭新执行入口，等待自动循环及所有手动检查/审计，再允许关闭数据库。"""
    await complete_before_cancellation(_drain_security_frequency(stop, worker), operation='关闭安全检查并排空审计')


async def _drain_security_frequency(stop: asyncio.Event, worker: asyncio.Task) -> None:
    """取消保护内等待已有执行；不取消正在提交审计的任务。"""
    stop.set()
    await security_frequency_service.drain()
    await worker
