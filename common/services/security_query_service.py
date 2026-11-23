"""安全日志与任务管理员查询：共享筛选计数、后端分页和真实字典，不提供日志修改。"""
from __future__ import annotations

import json
from datetime import datetime, time

from sqlalchemy import or_, select

from common.models.data_dictionary import XYDataDictionary
from common.models.security_log import SecurityLog
from common.models.security_task import (
    SECURITY_DICTIONARIES, SECURITY_INTERVAL_SECONDS, SECURITY_METHODS, SECURITY_RESULTS, SecurityTask,
)
from common.services.registration_log_query_service import _parse_date
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
        start, end = _parse_date(start_date, '开始日期'), _parse_date(end_date, '结束日期')
        if start and end and start > end:
            raise ValueError('开始日期不能晚于结束日期')
        if start:
            filters.append(SecurityLog.started_at >= start)
        if end:
            filters.append(SecurityLog.started_at <= datetime.combine(end.date(), time.max))
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
            order_by=[SecurityTask.id], page=page, page_size=page_size)
        now = get_beijing_now_naive()
        return {'items': [{
            # 运行间隔来自执行器统一常量；旧表NULL或遗留值不能伪装成当前真实调度间隔。
            'id': row.id, 'task_code': row.task_code, 'interval_seconds': SECURITY_INTERVAL_SECONDS,
            'next_run_at': safe_isoformat(row.next_run_at), 'last_run_at': safe_isoformat(row.last_run_at),
            'last_result': row.last_result, 'last_message': row.last_message,
            'running': bool(row.lease_id and row.lease_expires_at and row.lease_expires_at > now),
            'execution_id': row.lease_id, 'lease_expires_at': safe_isoformat(row.lease_expires_at),
        } for row in rows], 'total': total, 'page': page, 'page_size': page_size,
            'pages': (total + page_size - 1) // page_size, 'dictionaries': await self.dictionaries()}

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
