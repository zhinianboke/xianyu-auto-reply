"""原定时任务管理器的安全任务接入，保持所有历史任务及其调度实现。"""
from __future__ import annotations

import asyncio

from app.services.scheduled_task_service import ScheduledTaskService
from app.services.scheduler.security_frequency_task import SecurityFrequencyTask
from app.services.scheduler_service import SchedulerService
from common.db.session import async_session_maker
from common.models.security_task import SECURITY_TASK_CODE
from common.services.audit_writer import report_safely


class ScheduledTaskManager(SchedulerService):
    """复用原调度器，新增一项安全检查；不替换历史任务配置或执行逻辑。"""

    def __init__(self):
        """初始化原任务实例及安全任务适配器。"""
        super().__init__()
        self.security_task = SecurityFrequencyTask()
        self._stopping_tasks: set[asyncio.Task] = set()

    def start(self) -> None:
        """原启动流程中一并注册安全任务循环，启停配置来自原表。"""
        if not self._running:
            super().start()
            self.security_task.start()

    def stop(self) -> None:
        """保存原循环句柄后停止调度，供close等待取消收尾再释放数据库。"""
        self.security_task.stop()
        handles = {handle for name, handle in vars(self).items()
                   if name.endswith('_task_handle') and isinstance(handle, asyncio.Task)}
        self._stopping_tasks.update(handles)
        super().stop()
        for handle in handles:
            if not handle.done() and not handle.cancelling():
                handle.cancel()

    async def close(self) -> None:
        """等待安全审计及原任务取消收尾，数据库由服务生命周期最后关闭。"""
        self.stop()
        try:
            await self.security_task.close()
        finally:
            handles = tuple(self._stopping_tasks)
            results = await asyncio.gather(*handles, return_exceptions=True)
            self._stopping_tasks.difference_update(handles)
            for result in results:
                if isinstance(result, Exception):
                    report_safely('原定时任务关闭收尾失败', result)

    async def reload_task_config(self, task_code: str) -> None:
        """原刷新接口同时唤醒安全任务，安全配置故障向调用方传播。"""
        if task_code == SECURITY_TASK_CODE:
            async with async_session_maker() as session:
                await ScheduledTaskService(session).load_task_config(task_code)
            self.security_task.wakeup.set()
        else:
            await super().reload_task_config(task_code)

    async def reload_all_configs(self) -> None:
        """保留原任务刷新，并刷新新增安全任务。"""
        await super().reload_all_configs()
        await self.reload_task_config(SECURITY_TASK_CODE)

    def get_task_status(self) -> dict:
        """原状态接口只追加安全任务状态。"""
        status = super().get_task_status()
        handle = self.security_task.handle
        status['tasks'][SECURITY_TASK_CODE] = {
            'config': ScheduledTaskService.get_cached_config(SECURITY_TASK_CODE),
            'task_running': bool(handle and not handle.done()),
        }
        return status

    async def trigger_task(self, task_code: str, owner_id: int | None = None) -> dict | None:
        """原手动执行入口追加安全分派，其余任务仍走原执行逻辑。"""
        if task_code == SECURITY_TASK_CODE:
            return await self.security_task.execute(owner_id)
        return await super().trigger_task(task_code)


def get_scheduler_service() -> ScheduledTaskManager:
    """复用原单例槽，历史调用原getter也取得同一管理器。"""
    if SchedulerService._instance is None:
        SchedulerService._instance = ScheduledTaskManager()
    return SchedulerService._instance
