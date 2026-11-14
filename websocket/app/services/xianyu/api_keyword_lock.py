"""API关键词与自动发货共用订单锁，并在长时间请求期间续期。"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

from loguru import logger

from common.db.redis_client import release_delivery_lock, try_acquire_delivery_lock


class ApiKeywordOrderBusy(ValueError):
    """订单正在处理或无法获得有效发货锁。"""


@asynccontextmanager
async def api_keyword_order_lock(instance, order_no: str):
    """获取跨进程及账号实例订单锁，返回检查锁有效性的函数，退出时释放并停止续期。"""
    result = await try_acquire_delivery_lock(order_no, expire=120, holder_info=instance.cookie_id, wait_timeout=0)
    if not result.success:
        reason = "发货锁服务不可用，请稍后重试" if result.has_error else "该订单正在处理中，请稍后重试"
        raise ApiKeywordOrderBusy(reason)
    local_lock = None
    local_acquired = False
    renewal = None
    lost = False

    async def renew():
        """每30秒续期共享Redis锁；丢失后停止后续请求和确认发货。"""
        nonlocal lost
        try:
            while True:
                await asyncio.sleep(30)
                if not await result.lock.extend():
                    lost = True
                    logger.error("API关键词订单锁续期失败: order_no={}", order_no)
                    return
        except Exception:  # noqa: BLE001
            lost = True
            logger.exception("API关键词订单锁续期异常: order_no={}", order_no)

    async def ensure_owned():
        """在关键操作之前校验Redis锁仍归当前处理持有。"""
        if lost or not await result.lock.extend():
            raise ApiKeywordOrderBusy("订单处理锁已失效，已停止后续发货操作，请核对订单")

    try:
        local_lock = instance._order_locks[order_no]
        instance._lock_usage_times[order_no] = time.time()
        try:
            await asyncio.wait_for(local_lock.acquire(), timeout=5)
        except TimeoutError as exc:
            raise ApiKeywordOrderBusy("该订单正在处理中，请稍后重试") from exc
        local_acquired = True
        instance._lock_usage_times[order_no] = time.time()
        renewal = asyncio.create_task(renew())
        yield ensure_owned
    finally:
        if renewal is not None:
            renewal.cancel()
            await asyncio.gather(renewal, return_exceptions=True)
        if local_acquired:
            instance._lock_usage_times[order_no] = time.time()
            local_lock.release()
        if not await release_delivery_lock(result):
            logger.error("API关键词订单锁释放失败: order_no={}", order_no)
