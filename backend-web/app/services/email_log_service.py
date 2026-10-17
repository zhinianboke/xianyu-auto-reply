"""
邮件发送日志查询服务

功能：
1. 管理员分页查询全部邮件发送日志
2. 支持按收件邮箱关键字、触发操作、发送结果、时间区间筛选
3. 从数据字典读取触发操作和发送结果的中文名称
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.data_dictionary import XYDataDictionary
from common.models.email_log import XYEmailLog
from common.services.email_log_service import EMAIL_SEND_RESULT_FAILURE, EMAIL_SEND_RESULT_SUCCESS
from common.utils.pagination import build_pagination_response, execute_paginated_with_filters
from common.utils.time_utils import safe_isoformat

DICT_TYPE_EMAIL_TRIGGER_OPERATION = "email_trigger_operation"
DICT_TYPE_EMAIL_SEND_RESULT = "email_send_result"


class EmailLogService:
    """邮件发送日志查询服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_logs(
        self,
        *,
        recipient_email: str | None = None,
        trigger_operation: str | None = None,
        send_result: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """分页查询邮件发送日志。

        Args:
            recipient_email: 收件邮箱关键字。
            trigger_operation: 触发操作枚举值。
            send_result: 发送结果，success 或 failure。
            start_date: 开始日期 YYYY-MM-DD。
            end_date: 结束日期 YYYY-MM-DD。
            page: 页码。
            page_size: 每页数量。
        Returns:
            标准分页字典。
        """
        filters: list[Any] = []
        if recipient_email:
            keyword = recipient_email.strip()
            if keyword:
                filters.append(XYEmailLog.recipient_email.ilike(f"%{keyword}%"))
        if trigger_operation:
            filters.append(XYEmailLog.trigger_operation == trigger_operation.strip())
        if send_result in (EMAIL_SEND_RESULT_SUCCESS, EMAIL_SEND_RESULT_FAILURE):
            filters.append(XYEmailLog.success.is_(send_result == EMAIL_SEND_RESULT_SUCCESS))
        elif send_result:
            raise ValueError("发送结果参数无效，只支持 success 或 failure")
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("开始日期格式不正确，应为 YYYY-MM-DD") from exc
            filters.append(XYEmailLog.created_at >= start_dt)
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            except ValueError as exc:
                raise ValueError("结束日期格式不正确，应为 YYYY-MM-DD") from exc
            filters.append(XYEmailLog.created_at <= end_dt)
        if start_date and end_date and start_dt > end_dt:
            raise ValueError("开始日期不能晚于结束日期")

        logs, total = await execute_paginated_with_filters(
            self.session,
            XYEmailLog,
            filters=filters,
            order_by=[XYEmailLog.created_at.desc(), XYEmailLog.id.desc()],
            page=page,
            page_size=page_size,
        )
        items = [
            {
                "id": log.id,
                "owner_id": log.owner_id,
                "recipient_email": log.recipient_email,
                "trigger_operation": log.trigger_operation,
                "success": bool(log.success),
                "client_ip": log.client_ip,
                "result_message": log.result_message,
                "created_at": safe_isoformat(log.created_at),
            }
            for log in logs
        ]
        return build_pagination_response(items, total, page, page_size)

    async def get_options(self) -> dict[str, list[dict[str, Any]]]:
        """读取邮件日志相关筛选枚举及中文名称。"""
        result = await self.session.execute(
            select(XYDataDictionary)
            .where(
                XYDataDictionary.dict_type.in_(
                    [DICT_TYPE_EMAIL_TRIGGER_OPERATION, DICT_TYPE_EMAIL_SEND_RESULT]
                ),
                XYDataDictionary.enabled.is_(True),
            )
            .order_by(XYDataDictionary.dict_type.asc(), XYDataDictionary.sort_order.asc(), XYDataDictionary.id.asc())
        )
        options: dict[str, list[dict[str, Any]]] = {
            "trigger_operations": [],
            "send_results": [],
        }
        for item in result.scalars().all():
            target = (
                options["trigger_operations"]
                if item.dict_type == DICT_TYPE_EMAIL_TRIGGER_OPERATION
                else options["send_results"]
                if item.dict_type == DICT_TYPE_EMAIL_SEND_RESULT
                else None
            )
            if target is not None:
                target.append({"value": item.dict_value, "label": item.dict_label})
        return options


__all__ = ["EmailLogService"]
