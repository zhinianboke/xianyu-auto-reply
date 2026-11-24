"""原定时任务表统一查询：保留历史ID、配置和旧数组格式，新增后端分页。"""
from __future__ import annotations

from sqlalchemy import func, select

from common.models.scheduled_task import ScheduledTask
from common.models.security_task import SECURITY_TASK_CODE, SecurityTask
from common.services.scheduled_task_config_service import serialize_scheduled_task
from common.services.security_query_service import SecurityQueryService


class ScheduledTaskQueryService:
    """所有系统任务读取原表；安全状态只用于展示真实执行结果。"""

    def __init__(self, session):
        """参数为项目统一依赖提供的数据库会话。"""
        self.session = session

    async def list_legacy(self) -> list[dict]:
        """旧客户端未提交分页参数时，返回原任务数组且字段保持兼容。"""
        rows = await self.session.execute(select(ScheduledTask).order_by(ScheduledTask.id))
        return [serialize_scheduled_task(task) for task in rows.scalars()]

    async def list_page(self, *, page: int = 1, page_size: int = 20) -> dict:
        """同一原表分页，安全结果单独补充，避免UNION提升长文本元数据。"""
        SecurityQueryService.validate_pagination(page, page_size)
        total = int((await self.session.execute(select(func.count()).select_from(ScheduledTask))).scalar_one())
        pages = (total + page_size - 1) // page_size
        page = min(page, max(pages, 1))
        rows = (await self.session.execute(select(ScheduledTask).order_by(ScheduledTask.id)
            .offset((page - 1) * page_size).limit(page_size))).scalars().all()
        items = []
        for task in rows:
            data = serialize_scheduled_task(task)
            if task.task_code == SECURITY_TASK_CODE:
                state = (await self.session.execute(select(SecurityTask).where(
                    SecurityTask.task_code == SECURITY_TASK_CODE))).scalar_one_or_none()
                if state is None:
                    raise RuntimeError('安全执行状态未初始化，请检查数据库自检结果')
                data |= SecurityQueryService.serialize_task(state, task)
            items.append(data)
        dictionaries = await SecurityQueryService(self.session).dictionaries()
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size,
                'pages': pages, 'dictionaries': dictionaries}
