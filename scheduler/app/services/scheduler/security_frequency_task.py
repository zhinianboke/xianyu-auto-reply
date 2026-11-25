"""安全频率任务封装：与商品定时发布一样，只调用公共业务执行器。"""
from __future__ import annotations

from common.services.security_frequency_service import security_frequency_service


class SchedulerSecurityFrequencyTask:
    """统计与审计使用公共服务，调度由原SchedulerService管理。"""

    def start(self) -> None:
        """复用服务启动钩子，关闭后再次启动允许执行新的业务检查。"""
        security_frequency_service.closing = False

    async def execute(self, owner_id: int | None = None) -> dict | None:
        """执行一轮安全检查；管理员ID仅用于真实手动执行审计。"""
        method = 'manual' if owner_id is not None else 'auto'
        return await security_frequency_service.execute(method, owner_id)

    async def close(self) -> None:
        """服务关闭时等待已经开始的扫描和审计完成。"""
        await security_frequency_service.drain()


security_frequency_task_service = SchedulerSecurityFrequencyTask()
