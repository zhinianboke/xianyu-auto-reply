"""原定时任务与安全任务统一查询：原表只读、稳定后端分页、保留旧客户端数组格式。"""
from __future__ import annotations

from sqlalchemy import func, select

from common.models.scheduled_task import ScheduledTask
from common.models.security_task import SECURITY_TASK_CODE, SecurityTask
from common.services.security_query_service import SecurityQueryService
from common.utils.time_utils import safe_isoformat


class ScheduledTaskQueryService:
    """复用请求会话读取两个原表，不复制、覆盖或初始化历史任务。"""

    def __init__(self, session):
        """参数为项目统一依赖提供的数据库会话。"""
        self.session = session

    @staticmethod
    def serialize_task(task: ScheduledTask) -> dict:
        """保留原任务ID、间隔、启停和时间；没有存储的运行结果不补造。"""
        return {key: getattr(task, key) for key in (
            'id', 'task_code', 'task_name', 'interval_seconds', 'enabled', 'description',
        )} | {'created_at': safe_isoformat(task.created_at), 'updated_at': safe_isoformat(task.updated_at)}

    async def list_legacy(self) -> list[dict]:
        """旧客户端未提交分页参数时，返回原任务数组且字段保持兼容。"""
        rows = await self.session.execute(select(ScheduledTask).order_by(ScheduledTask.id))
        return [self.serialize_task(task) for task in rows.scalars()]

    async def list_page(self, *, page: int = 1, page_size: int = 20) -> dict:
        """原任务按原ID排序，安全任务追加末尾；两表共用总数、偏移和每页条数。

        分表读取原始列，避免UNION提升TEXT元数据触发Windows asyncmy整数溢出。
        所有查询共用当前事务，保留已禁用和下线任务，不触碰历史执行日志。
        """
        SecurityQueryService.validate_pagination(page, page_size)
        legacy_total = int((await self.session.execute(select(func.count()).select_from(ScheduledTask))).scalar_one())
        security_filter = SecurityTask.task_code == SECURITY_TASK_CODE
        security_total = int((await self.session.execute(
            select(func.count()).select_from(SecurityTask).where(security_filter))).scalar_one())
        if not security_total:
            raise RuntimeError('安全频率任务未初始化，请检查后端数据库自检结果')
        total = legacy_total + security_total
        pages = (total + page_size - 1) // page_size
        page = min(page, max(pages, 1))
        offset = (page - 1) * page_size
        items = []
        if offset < legacy_total:
            rows = await self.session.execute(select(ScheduledTask).order_by(ScheduledTask.id)
                .offset(offset).limit(page_size))
            items.extend(self.serialize_task(row) | {'task_source': 'scheduled'} for row in rows.scalars())
        remaining = page_size - len(items)
        dictionaries = await SecurityQueryService(self.session).dictionaries()
        if remaining:
            rows = await self.session.execute(select(SecurityTask).where(security_filter).order_by(SecurityTask.id)
                .offset(max(offset - legacy_total, 0)).limit(remaining))
            for row in rows.scalars():
                name = next((item['label'] for item in dictionaries['security_task_name']
                             if item['value'] == row.task_code), None)
                items.append(SecurityQueryService.serialize_task(row) | {
                    'task_source': 'security', 'task_name': name,
                })
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size,
                'pages': pages, 'dictionaries': dictionaries}
