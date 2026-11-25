"""管理员注册日志查询：组合筛选、后端分页、关联用户和数据库字典中文名称。"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.data_dictionary import XYDataDictionary
from common.models.registration_log import (
    REGISTRATION_OPERATION_DICTIONARY,
    REGISTRATION_OPERATIONS,
    REGISTRATION_STATUS_DICTIONARY,
    REGISTRATION_STATUSES,
    RegistrationLog,
)
from common.models.user import User
from common.utils.date_filters import date_range_conditions, parse_filter_date as _parse_date  # noqa: F401 -- 保留旧公共导入路径
from common.utils.pagination import execute_paginated_with_filters
from common.utils.time_utils import safe_isoformat


class RegistrationLogQueryService:
    """仅查询注册日志，权限由统一管理员依赖校验，不提供更新或删除方法。"""

    def __init__(self, session: AsyncSession) -> None:
        """保存当前请求数据库会话，不创建独立引擎或跨请求复用会话。"""
        self.session = session

    async def list_logs(
        self, *, keyword: str | None = None, client_ip: str | None = None,
        operation: str | None = None, status: str | None = None,
        start_date: str | None = None, end_date: str | None = None,
        page: int = 1, page_size: int = 20,
    ) -> dict:
        """查询注册日志与中文字典，所有条件共用计数和列表并使用参数绑定。

        Args:
            keyword: 提交用户名、注册邮箱、真实关联用户的用户名或邮箱，数字也匹配用户ID。
            client_ip: 完整 IP 或片段，去除首尾空格后按字面包含匹配。
            operation: 注册操作枚举，空值表示不限。
            status: success/failed 注册结果，空值表示不限。
            start_date: 开始日期，包含北京时间当天零点。
            end_date: 结束日期，包含北京时间当天全部时间。
            page: 从 1 开始的页码。
            page_size: 每页 10/20/50/100 条。
        Returns:
            items、total、分页信息及操作/结果字典选项，保留禁用字典用于历史中文展示。
        """
        if page < 1:
            raise ValueError("页码必须大于零")
        if page_size not in (10, 20, 50, 100):
            raise ValueError("每页条数只能选择10、20、50或100")
        operation_value, status_value = (operation or "").strip(), (status or "").strip()
        if operation_value and operation_value not in REGISTRATION_OPERATIONS:
            raise ValueError("注册操作无效，请选择有效的注册操作")
        if status_value and status_value not in REGISTRATION_STATUSES:
            raise ValueError("注册结果无效，请选择成功或失败")
        filters = date_range_conditions(RegistrationLog.created_at, start_date, end_date)
        keyword_value = (keyword or "").strip()
        if keyword_value:
            related_user_ids = select(User.id).where(or_(
                User.username.icontains(keyword_value, autoescape=True),
                User.email.icontains(keyword_value, autoescape=True),
            ))
            conditions = [
                RegistrationLog.username.icontains(keyword_value, autoescape=True),
                RegistrationLog.email.icontains(keyword_value, autoescape=True),
                RegistrationLog.owner_id.in_(related_user_ids),
            ]
            # 超长数字仍以真实文本查询，不传入超过 BIGINT 范围的整型参数。
            if keyword_value.isascii() and keyword_value.isdigit() and len(keyword_value) <= 19:
                user_id = int(keyword_value)
                if user_id <= 9223372036854775807:
                    conditions.append(RegistrationLog.owner_id == user_id)
            filters.append(or_(*conditions))
        ip_value = (client_ip or "").strip()
        if ip_value:
            filters.append(RegistrationLog.client_ip.icontains(ip_value, autoescape=True))
        if operation_value:
            filters.append(RegistrationLog.operation == operation_value)
        if status_value:
            # 历史补字段允许 NULL，保留原布尔语义；不按非空 0/1 字段机械改写。
            filters.append(RegistrationLog.success.is_(status_value == "success"))
        logs, total = await execute_paginated_with_filters(
            self.session, RegistrationLog, filters=filters,
            order_by=[RegistrationLog.created_at.desc(), RegistrationLog.id.desc()],
            page=page, page_size=page_size,
        )
        owner_ids = {log.owner_id for log in logs if log.owner_id is not None}
        owners = dict((await self.session.execute(select(User.id, User.username).where(
            User.id.in_(owner_ids)
        ))).all()) if owner_ids else {}
        dictionaries = (await self.session.execute(select(
            XYDataDictionary.dict_type, XYDataDictionary.dict_value,
            XYDataDictionary.dict_label, XYDataDictionary.enabled,
        ).where(XYDataDictionary.dict_type.in_(
            (REGISTRATION_OPERATION_DICTIONARY, REGISTRATION_STATUS_DICTIONARY)
        )).order_by(XYDataDictionary.sort_order, XYDataDictionary.id))).all()
        options = {REGISTRATION_OPERATION_DICTIONARY: [], REGISTRATION_STATUS_DICTIONARY: []}
        for dict_type, value, label, enabled in dictionaries:
            options[dict_type].append({"value": value, "label": label, "enabled": bool(enabled)})
        return {
            "items": [{
                "id": log.id, "owner_id": log.owner_id, "owner_username": owners.get(log.owner_id),
                "username": log.username, "email": log.email, "operation": log.operation,
                "success": None if log.success is None else bool(log.success),
                "client_ip": log.client_ip, "message": log.message,
                "created_at": safe_isoformat(log.created_at),
            } for log in logs],
            "total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
            "operation_options": options[REGISTRATION_OPERATION_DICTIONARY],
            "status_options": options[REGISTRATION_STATUS_DICTIONARY],
        }
