"""原调度器中的安全频率任务：共用配置加载、执行入口和关闭流程。"""
from __future__ import annotations

import asyncio

from app.services.scheduled_task_service import ScheduledTaskService
from common.db.session import async_session_maker
from common.models.security_task import SECURITY_TASK_CODE
from common.services.audit_writer import report_safely
from common.services.security_frequency_service import security_frequency_service
from common.utils.async_cleanup import complete_before_cancellation


class SecurityFrequencyTask:
    """仅负责原scheduler的调度接入；统计、占用和审计继续复用公共执行器。"""

    def __init__(self):
        """创建可唤醒的等待状态，不创建数据库或Redis连接池。"""
        self.stopping = False
        self.wakeup = asyncio.Event()
        self.handle: asyncio.Task | None = None

    def start(self) -> None:
        """原调度器启动时注册循环；数据库默认开关为停止。"""
        if self.handle and not self.handle.done():
            return
        self.stopping = False
        security_frequency_service.closing = False
        self.handle = asyncio.create_task(self.run())

    def stop(self) -> None:
        """停止后续调度并唤醒等待，不取消已有执行和审计。"""
        self.stopping = True
        security_frequency_service.closing = True
        self.wakeup.set()

    async def close(self) -> None:
        """生命周期退出时先排空自动、手动执行，再允许释放数据库资源。"""
        await complete_before_cancellation(self._drain(), operation='原调度器关闭安全检查并排空审计')

    async def _drain(self) -> None:
        """保护已开始的执行，等待循环退出，不另行触发检查。"""
        self.stop()
        await security_frequency_service.drain()
        if self.handle:
            await self.handle

    async def execute(self, owner_id: int | None = None) -> dict:
        """由已认证内部接口传入管理员ID，停止自动调度时仍支持手动检查。"""
        return await security_frequency_service.execute('manual', owner_id)

    async def run(self) -> None:
        """原任务配置控制自动检查；执行器在事务内再次核对开关及持久化到期时间。"""
        while not self.stopping:
            self.wakeup.clear()
            try:
                async with async_session_maker() as session:
                    config = await ScheduledTaskService(session).load_task_config(SECURITY_TASK_CODE)
                if config['enabled'] and not self.stopping:
                    await security_frequency_service.execute()
            except Exception as exc:  # noqa: BLE001 -- 调度边界使用公共日志方法记录完整异常堆栈。
                report_safely(f'定时任务执行失败 task_code={SECURITY_TASK_CODE} '
                              f'exception_type={type(exc).__name__} exception={exc}', exc)
            # 到期时间由审计事务保存，短等待兼容手动执行及多实例到期竞争。
            try:
                await asyncio.wait_for(self.wakeup.wait(), timeout=1)
            except TimeoutError:
                continue
