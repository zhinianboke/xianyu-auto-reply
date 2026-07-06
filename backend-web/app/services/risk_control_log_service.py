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

from sqlalchemy import select, func, case, and_
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
        统计当日（北京时间）风控处理成功率（含总体 / 本机 / 远程三个维度）

        - 总成功率   = 当日成功记录数 / 当日总记录数
        - 本机成功率 = 当日本机成功记录数 / 当日本机总记录数
        - 远程成功率 = 当日远程成功记录数 / 当日远程总记录数

        说明：
        - 处理中（'processing'）与已取消（'cancelled'）的记录不计入成功率统计，分子和分母都排除，
          成功率仅统计已出结果（success/failed）的记录；处理中记录单独以 processing 字段返回。
        - 远程口径为 call_type == 'remote'；其余（含 'local' 与 NULL）一律计入本机，
          保证 本机数 + 远程数 == 总数，三个维度各自使用自己的分母，避免分母用错。
        - 普通用户仅统计自己的账号数据，管理员统计全部数据（由 owner_id 控制）。

        Args:
            owner_id: 所有者ID筛选，None 表示不限制（管理员）

        Returns:
            包含 date 及 total/success/rate、local_*、remote_*、processing 的字典
        """
        now = get_beijing_now_naive()
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        # 当日范围过滤条件（仅限定当天与所有者，处理中状态在各聚合中单独区分）
        day_filters = [
            XYRiskControlLog.created_at >= start_dt,
            XYRiskControlLog.created_at <= end_dt,
        ]
        if owner_id is not None:
            day_filters.append(XYRiskControlLog.owner_id == owner_id)

        is_success = XYRiskControlLog.processing_status == "success"
        is_remote = XYRiskControlLog.call_type == "remote"
        is_processing = XYRiskControlLog.processing_status == "processing"
        # 成功率口径：仅统计已出结果的记录，排除处理中（processing）与已取消（cancelled）
        is_settled = XYRiskControlLog.processing_status.notin_(["processing", "cancelled"])

        # 一次查询用条件聚合得到：总数、成功数、远程总数、远程成功数、处理中数
        # 成功率相关的 total/success/remote_* 均只计入已出结果（settled）记录，
        # processing 单独统计当日处理中记录数，两者互不影响。
        stmt = (
            select(
                func.coalesce(func.sum(case((is_settled, 1), else_=0)), 0).label("total"),
                func.coalesce(
                    func.sum(case((and_(is_settled, is_success), 1), else_=0)), 0
                ).label("success"),
                func.coalesce(
                    func.sum(case((and_(is_settled, is_remote), 1), else_=0)), 0
                ).label("remote_total"),
                func.coalesce(
                    func.sum(case((and_(is_settled, is_remote, is_success), 1), else_=0)), 0
                ).label("remote_success"),
                func.coalesce(func.sum(case((is_processing, 1), else_=0)), 0).label("processing"),
            )
            .select_from(XYRiskControlLog)
            .where(*day_filters)
        )
        row = (await self.session.execute(stmt)).one()

        total = int(row.total or 0)
        success = int(row.success or 0)
        remote_total = int(row.remote_total or 0)
        remote_success = int(row.remote_success or 0)
        processing = int(row.processing or 0)

        # 本机 = 总数 - 远程，保证两类相加等于总数（NULL/local 都归本机）
        local_total = total - remote_total
        local_success = success - remote_success

        def _rate(s: int, t: int) -> float:
            return round(s / t * 100, 2) if t > 0 else 0.0

        return {
            "date": start_dt.strftime("%Y-%m-%d"),
            "total": total,
            "success": success,
            "rate": _rate(success, total),
            "local_total": local_total,
            "local_success": local_success,
            "local_rate": _rate(local_success, local_total),
            "remote_total": remote_total,
            "remote_success": remote_success,
            "remote_rate": _rate(remote_success, remote_total),
            "processing": processing,
        }
