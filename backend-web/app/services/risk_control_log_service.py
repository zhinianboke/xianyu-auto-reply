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

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.risk_control_log import XYRiskControlLog
from common.utils.pagination import execute_paginated_with_filters


from common.utils.time_utils import safe_isoformat, get_beijing_now_naive
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
        call_type: Optional[str] = None,
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
            call_type: 调用类型筛选（local-本机/remote-远程）
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

        # 调用类型筛选（local-本机/remote-远程）
        if call_type:
            filters.append(XYRiskControlLog.call_type == call_type)

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
                "call_type": log.call_type,
                "call_user": log.call_user,
                "error_message": log.error_message,
                "created_at": safe_isoformat(log.created_at),
                "updated_at": safe_isoformat(log.updated_at),
            }
            for log in logs
        ]
        return items, total

    async def get_today_success_rate(self, *, owner_id: int | None = None) -> dict:
        """
        统计当日（北京时间）风控处理成功率

        成功率 = 当日处理成功记录数 / 当日总记录数。
        普通用户仅统计自己的账号数据，管理员统计全部数据（由 owner_id 控制）。

        Args:
            owner_id: 所有者ID筛选，None 表示不限制（管理员）

        Returns:
            {"date": "YYYY-MM-DD", "total": 总数, "success": 成功数, "rate": 成功率(%)}
        """
        now = get_beijing_now_naive()
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        # 当日范围过滤条件（成功数与总数共用）
        base_filters = [
            XYRiskControlLog.created_at >= start_dt,
            XYRiskControlLog.created_at <= end_dt,
        ]
        if owner_id is not None:
            base_filters.append(XYRiskControlLog.owner_id == owner_id)

        total_stmt = select(func.count()).select_from(XYRiskControlLog).where(*base_filters)
        total = (await self.session.execute(total_stmt)).scalar() or 0

        success_stmt = (
            select(func.count())
            .select_from(XYRiskControlLog)
            .where(*base_filters, XYRiskControlLog.processing_status == "success")
        )
        success = (await self.session.execute(success_stmt)).scalar() or 0

        rate = round(success / total * 100, 2) if total > 0 else 0.0

        return {
            "date": start_dt.strftime("%Y-%m-%d"),
            "total": total,
            "success": success,
            "rate": rate,
        }
