"""安全日志与任务管理员查询：共享筛选计数、后端分页和真实字典，不提供日志修改。"""
from __future__ import annotations

import json

from sqlalchemy import or_, select

from common.models.data_dictionary import XYDataDictionary
from common.models.scheduled_task import ScheduledTask
from common.models.security_log import SecurityLog
from common.models.security_task import (
    SECURITY_DICTIONARIES,
    SECURITY_METHODS,
    SECURITY_RESULTS,
    SECURITY_TASK_CODE,
    SecurityTask,
)
from common.utils.date_filters import date_range_conditions
from common.utils.pagination import execute_paginated_with_filters
from common.utils.time_utils import get_beijing_now_naive, safe_isoformat


class SecurityQueryService:
    """只查询安全审计和调度状态；管理员权限由统一依赖负责。"""

    def __init__(self, session):
        """复用当前请求会话，不创建引擎或工厂。"""
        self.session = session

    async def dictionaries(self) -> dict:
        """读取数据库中文名称，保留禁用项用于历史展示，不硬编码映射。"""
        options = {key: [] for key in SECURITY_DICTIONARIES}
        rows = await self.session.execute(select(XYDataDictionary).where(
            XYDataDictionary.dict_type.in_(tuple(options))).order_by(XYDataDictionary.sort_order, XYDataDictionary.id))
        for item in rows.scalars():
            options[item.dict_type].append({'value': item.dict_value, 'label': item.dict_label, 'enabled': item.enabled})
        return options

    async def list_logs(self, *, page=1, page_size=20, keyword=None, added_ip=None,
                        execution_method=None, result=None, start_date=None, end_date=None) -> dict:
        """组合查询关键字、新增IP字面包含、方式结果与北京时间区间，总数列表共用条件。"""
        self.validate_pagination(page, page_size)
        filters = []
        keyword, added_ip = (keyword or '').strip(), (added_ip or '').strip()
        execution_method, result = (execution_method or '').strip(), (result or '').strip()
        if execution_method and execution_method not in SECURITY_METHODS:
            raise ValueError('执行方式无效，请选择有效的执行方式')
        if result and result not in SECURITY_RESULTS:
            raise ValueError('执行结果无效，请选择有效的执行结果')
        if keyword:
            filters.append(or_(SecurityLog.added_suffixes.icontains(keyword, autoescape=True),
                               SecurityLog.message.icontains(keyword, autoescape=True),
                               SecurityLog.execution_id.icontains(keyword, autoescape=True)))
        if added_ip:
            filters.append(SecurityLog.added_ips.icontains(added_ip, autoescape=True))
        if execution_method:
            filters.append(SecurityLog.execution_method == execution_method)
        if result:
            filters.append(SecurityLog.result == result)
        filters.extend(date_range_conditions(SecurityLog.started_at, start_date, end_date))
        rows, total = await execute_paginated_with_filters(self.session, SecurityLog, filters=filters,
            order_by=[SecurityLog.started_at.desc(), SecurityLog.id.desc()], page=page, page_size=page_size)
        return {'items': [self.serialize_log(item) for item in rows], 'total': total, 'page': page,
                'page_size': page_size, 'pages': (total + page_size - 1) // page_size,
                'dictionaries': await self.dictionaries()}

    async def get_log(self, log_id: int) -> dict:
        """返回真实完整详情，JSON损坏明确报错，不用模拟或空详情兜底。"""
        record = await self.session.get(SecurityLog, log_id)
        if record is None:
            raise ValueError('安全日志不存在')
        data = self.serialize_log(record)
        try:
            data['details'] = json.loads(record.details) if record.details else None
        except (json.JSONDecodeError, TypeError) as exc:
            raise RuntimeError('安全日志详情格式损坏，请联系管理员检查原始记录') from exc
        data['dictionaries'] = await self.dictionaries()
        return data

    async def list_tasks(self, *, page=1, page_size=20) -> dict:
        """展示真实下次执行、上次结果及占用，不影响插件自有调度。"""
        self.validate_pagination(page, page_size)
        rows, total = await execute_paginated_with_filters(self.session, SecurityTask,
            filters=[SecurityTask.task_code == SECURITY_TASK_CODE], order_by=[SecurityTask.id], page=page, page_size=page_size)
        schedule = (await self.session.execute(select(ScheduledTask).where(
            ScheduledTask.task_code == SECURITY_TASK_CODE))).scalar_one_or_none()
        if schedule is None:
            raise RuntimeError('安全频率限制未接入原定时任务表，请检查启动自检结果')
        return {'items': [self.serialize_task(row, schedule) for row in rows], 'total': total, 'page': page, 'page_size': page_size,
            'pages': (total + page_size - 1) // page_size, 'dictionaries': await self.dictionaries()}

    @staticmethod
    def serialize_task(row: SecurityTask, schedule: ScheduledTask) -> dict:
        """统一序列化安全任务原始调度状态，供原定时任务列表与兼容接口复用。"""
        now = get_beijing_now_naive()
        return {
            'id': schedule.id, 'task_code': schedule.task_code, 'interval_seconds': schedule.interval_seconds,
            'enabled': bool(schedule.enabled),
            # 兼容旧字段；原调度器采用间隔循环，旧持久化时间不再是运行来源。
            'next_run_at': None,
            'last_run_at': safe_isoformat(row.last_run_at),
            'last_result': row.last_result, 'last_message': row.last_message,
            'running': bool(row.lease_id and row.lease_expires_at and row.lease_expires_at > now),
            'execution_id': row.lease_id, 'lease_expires_at': safe_isoformat(row.lease_expires_at),
        }

    @staticmethod
    def validate_pagination(page: int, page_size: int) -> None:
        """校验安全日志和任务共用分页约定，非法参数给出中文错误。"""
        if page < 1 or page_size not in (10, 20, 50, 100):
            raise ValueError('页码必须大于零，每页条数只能选择10、20、50或100')

    @staticmethod
    def serialize_log(log: SecurityLog) -> dict:
        """序列化实际新增与时间；历史缺字段保留空值，不能补造执行结果。"""
        return {key: getattr(log, key) for key in (
            'id', 'execution_id', 'owner_id', 'execution_method', 'result', 'message',
            'added_suffixes', 'added_ips',
        )} | {'started_at': safe_isoformat(log.started_at), 'finished_at': safe_isoformat(log.finished_at)}
