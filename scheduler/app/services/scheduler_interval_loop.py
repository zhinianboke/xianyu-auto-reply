"""原调度器的间隔循环：商品定时发布和安全频率限制共用同一执行流程。"""
from __future__ import annotations

import asyncio

from loguru import logger

from app.services.scheduled_task_service import ScheduledTaskService


class SchedulerIntervalLoop:
    """使用原配置缓存控制自动执行，手动执行继续走原任务触发接口。"""

    async def _run_interval_task_loop(self, task_code: str, task_name: str, task,
                                      *, default_interval: int, default_enabled: bool) -> None:
        """读取配置、执行一轮并等待间隔；参数为任务信息和既有默认值，无返回值。"""
        logger.info('[定时任务调度] {}任务循环开始', task_name)
        await self.reload_task_config(task_code)
        while self._running:
            config = ScheduledTaskService.get_cached_config(task_code) or {
                'interval_seconds': default_interval, 'enabled': default_enabled,
            }
            if config.get('enabled', default_enabled):
                try:
                    await task.execute()
                except asyncio.CancelledError:
                    logger.info('[定时任务调度] {}任务被取消', task_name)
                    break
                except Exception as exc:  # noqa: BLE001 -- 调度边界记录完整异常，继续下一轮。
                    logger.opt(exception=exc).error('[定时任务调度] {}任务执行异常: {}', task_name, exc)
            try:
                await asyncio.sleep(max(1, int(config.get('interval_seconds', default_interval))))
            except asyncio.CancelledError:
                break
        logger.info('[定时任务调度] {}任务循环结束', task_name)
