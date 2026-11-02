"""Scheduler 中唯一的商品定时发布 runner。"""
from __future__ import annotations

from app.core.config import get_settings
from common.services.scheduled_publish_task import ScheduledPublishTask


class SchedulerScheduledPublishTask:
    """封装公共商品定时发布服务，避免 scheduler 复制业务逻辑。"""

    def __init__(self) -> None:
        """使用 Scheduler 配置初始化公共任务服务。"""
        settings = get_settings()
        self._task = ScheduledPublishTask(static_dir=settings.static_dir)

    async def execute(self) -> None:
        """执行一次商品定时发布扫描。"""
        await self._task.execute()


scheduled_publish_task_service = SchedulerScheduledPublishTask()
