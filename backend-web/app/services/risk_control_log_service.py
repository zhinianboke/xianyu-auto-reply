"""
风控日志服务

功能：
1. 风控日志查询（支持分页）
2. 按账号筛选日志
3. 按时间范围筛选日志
4. 按处理状态筛选日志
5. 日志统计
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from common.models.risk_control_log import XYRiskControlLog
from common.utils.pagination import execute_paginated_with_filters


from common.utils.time_utils import safe_isoformat
class RiskControlLogService:
    """Read-only access to risk control logs."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_logs(
        self,
        *,
        owner_id: int | None = None,
        account_identifier: str | None = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        processing_status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """
        查询风控日志列表
        
        Args:
            owner_id: 所有者ID筛选
            account_identifier: 账号ID筛选
            start_date: 开始日期（格式：YYYY-MM-DD）
            end_date: 结束日期（格式：YYYY-MM-DD）
            processing_status: 处理状态筛选（success/failed/processing）
            limit: 每页数量
            offset: 偏移量
            
        Returns:
            (日志列表, 总数)
        """
        # 收集过滤条件（一次构建，后续由分页工具同时应用到 list 与 count 语句）
        filters: list = []

        if owner_id is not None:
            filters.append(XYRiskControlLog.owner_id == owner_id)

        # 账号筛选
        if account_identifier:
            filters.append(XYRiskControlLog.account_identifier == account_identifier)

        # 时间范围筛选（格式错误时静默跳过，与原逻辑一致）
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                filters.append(XYRiskControlLog.created_at >= start_dt)
            except ValueError:
                pass

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
                filters.append(XYRiskControlLog.created_at <= end_dt)
            except ValueError:
                pass

        # 处理状态筛选
        if processing_status:
            filters.append(XYRiskControlLog.processing_status == processing_status)

        logs, total = await execute_paginated_with_filters(
            self.session,
            XYRiskControlLog,
            filters=filters,
            order_by=[XYRiskControlLog.created_at.desc()],
            limit=limit,
            offset=offset,
        )

        items = [
            {
                "id": log.id,
                "cookie_id": log.account_identifier,
                "cookie_name": log.account_identifier,
                "event_type": log.event_type,
                "event_description": log.event_description,
                "processing_result": log.processing_result,
                "processing_status": log.processing_status,
                "captcha_engine": log.captcha_engine,
                "error_message": log.error_message,
                "created_at": safe_isoformat(log.created_at),
                "updated_at": safe_isoformat(log.updated_at),
            }
            for log in logs
        ]
        return items, total
