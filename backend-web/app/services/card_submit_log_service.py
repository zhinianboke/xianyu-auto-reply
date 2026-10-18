"""
卡密提交日志查询服务。

功能：
1. 管理员分页查询卡密提交日志
2. 支持按订单号、提交结果和日期范围筛选
3. 从数据字典读取提交结果中文名称
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.card_submit_log import XYCardSubmitLog
from common.models.data_dictionary import XYDataDictionary
from common.utils.pagination import build_pagination_response, execute_paginated_with_filters
from common.utils.time_utils import safe_isoformat


DICT_TYPE_CARD_SUBMIT_RESULT = "card_submit_result"


class CardSubmitLogService:
    """卡密提交日志查询服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_logs(
        self,
        *,
        order_no: str | None = None,
        submit_result: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """按筛选条件分页查询卡密提交日志。"""
        filters: list[Any] = []
        if order_no and order_no.strip():
            filters.append(XYCardSubmitLog.order_no.ilike(f"%{order_no.strip()}%"))
        if submit_result in {"success", "failure"}:
            filters.append(XYCardSubmitLog.success.is_(submit_result == "success"))
        elif submit_result:
            raise ValueError("提交结果参数无效，只支持 success 或 failure")

        start_dt: datetime | None = None
        end_dt: datetime | None = None
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("开始日期格式不正确，应为 YYYY-MM-DD") from exc
            filters.append(XYCardSubmitLog.created_at >= start_dt)
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
            except ValueError as exc:
                raise ValueError("结束日期格式不正确，应为 YYYY-MM-DD") from exc
            filters.append(XYCardSubmitLog.created_at <= end_dt)
        if start_dt and end_dt and start_dt > end_dt:
            raise ValueError("开始日期不能晚于结束日期")

        logs, total = await execute_paginated_with_filters(
            self.session,
            XYCardSubmitLog,
            filters=filters,
            order_by=[XYCardSubmitLog.created_at.desc(), XYCardSubmitLog.id.desc()],
            page=page,
            page_size=page_size,
        )
        items = [
            {
                "id": log.id,
                "owner_id": log.owner_id,
                "order_no": log.order_no,
                "response_body": log.response_body,
                "success": bool(log.success),
                "result_message": log.result_message,
                "created_at": safe_isoformat(log.created_at),
            }
            for log in logs
        ]
        return build_pagination_response(items, total, page, page_size)

    async def get_options(self) -> dict[str, list[dict[str, Any]]]:
        """读取卡密提交结果数据字典。"""
        result = await self.session.execute(
            select(XYDataDictionary)
            .where(
                XYDataDictionary.dict_type == DICT_TYPE_CARD_SUBMIT_RESULT,
                XYDataDictionary.enabled.is_(True),
            )
            .order_by(XYDataDictionary.sort_order.asc(), XYDataDictionary.id.asc())
        )
        return {
            "submit_results": [
                {"value": item.dict_value, "label": item.dict_label}
                for item in result.scalars().all()
            ]
        }


__all__ = ["CardSubmitLogService"]
