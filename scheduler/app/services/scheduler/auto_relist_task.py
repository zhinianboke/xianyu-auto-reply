"""Scheduler 中唯一的商品自动续售 runner。"""
from __future__ import annotations

from app.core.config import get_settings
from common.services.auto_relist_task import AutoRelistTask


class SchedulerAutoRelistTask:
    """封装公共自动续售服务，避免 scheduler 复制业务逻辑。"""

    def __init__(self) -> None:
        settings = get_settings()
        self._task = AutoRelistTask(
            static_dir=settings.static_dir,
            lease_seconds=settings.auto_relist_lease_seconds,
            batch_size=settings.auto_relist_batch_size,
            max_retries=settings.auto_relist_max_retries,
        )

    async def execute(self) -> None:
        """执行一次续售扫描。"""
        await self._task.execute()


auto_relist_task_service = SchedulerAutoRelistTask()
