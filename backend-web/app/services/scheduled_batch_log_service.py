"""
定时批次日志查询服务。

功能：
1. 统一补发货日志、补评价日志、擦亮日志的批次列表查询。
2. 使用候选批次预筛选优化批次分页统计查询。
3. 提供批次详情查询，减少 ORM 实体加载开销。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.scheduled_polish_log import ScheduledPolishLog
from common.models.scheduled_rate_log import ScheduledRateLog
from common.models.scheduled_redelivery_log import ScheduledRedeliveryLog
from common.models.scheduled_red_flower_log import ScheduledRedFlowerLog
from common.models.scheduled_token_renewal_log import ScheduledTokenRenewalLog


from common.utils.time_utils import safe_isoformat
class ScheduledBatchLogService:
    """统一处理定时批次日志的列表与详情查询。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _parse_start_date(value: str | None) -> datetime | None:
        """解析开始日期，格式错误时返回空。"""
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None

    @staticmethod
    def _parse_end_date(value: str | None) -> datetime | None:
        """解析结束日期，格式错误时返回空，并补齐到当天结束时间。"""
        if not value:
            return None
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
            return parsed.replace(hour=23, minute=59, second=59)
        except ValueError:
            return None

    def _build_candidate_batch_ids_subquery(
        self,
        *,
        model: Any,
        start_dt: datetime | None,
        end_dt: datetime | None,
    ):
        """按创建时间先筛选候选批次，减少后续聚合扫描范围。"""
        stmt = select(model.batch_id.label("batch_id")).distinct()
        if start_dt is not None:
            stmt = stmt.where(model.created_at >= start_dt)
        if end_dt is not None:
            stmt = stmt.where(model.created_at <= end_dt)
        return stmt.subquery()

    def _build_summary_subquery(
        self,
        *,
        model: Any,
        start_dt: datetime | None,
        end_dt: datetime | None,
    ):
        """构建按批次聚合后的汇总子查询。"""
        stmt = select(
            model.batch_id.label("batch_id"),
            func.min(model.created_at).label("executed_at"),
            func.count().label("total_count"),
            func.sum(case((model.status == "success", 1), else_=0)).label("success_count"),
            func.sum(case((model.status == "failed", 1), else_=0)).label("failed_count"),
        )

        if start_dt is not None or end_dt is not None:
            candidate_batches = self._build_candidate_batch_ids_subquery(
                model=model,
                start_dt=start_dt,
                end_dt=end_dt,
            )
            stmt = stmt.join(candidate_batches, candidate_batches.c.batch_id == model.batch_id)

        stmt = stmt.group_by(model.batch_id)
        return stmt.subquery()

    @staticmethod
    def _apply_executed_at_filters(stmt: Any, summary_subquery: Any, start_dt: datetime | None, end_dt: datetime | None) -> Any:
        """对批次汇总结果按执行时间做最终过滤，保持原查询语义。"""
        if start_dt is not None:
            stmt = stmt.where(summary_subquery.c.executed_at >= start_dt)
        if end_dt is not None:
            stmt = stmt.where(summary_subquery.c.executed_at <= end_dt)
        return stmt

    async def _count_summary_rows(
        self,
        *,
        summary_subquery: Any,
        start_dt: datetime | None,
        end_dt: datetime | None,
    ) -> int:
        """统计当前筛选条件下的批次数量。"""
        stmt = select(func.count()).select_from(summary_subquery)
        stmt = self._apply_executed_at_filters(stmt, summary_subquery, start_dt, end_dt)
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def _list_batches(
        self,
        *,
        model: Any,
        start_date: str | None,
        end_date: str | None,
        page: int,
        page_size: int,
        total_key: str,
    ) -> tuple[list[dict[str, Any]], int]:
        """统一分页查询批次列表。"""
        start_dt = self._parse_start_date(start_date)
        end_dt = self._parse_end_date(end_date)
        offset = (page - 1) * page_size

        summary_subquery = self._build_summary_subquery(
            model=model,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        total = await self._count_summary_rows(
            summary_subquery=summary_subquery,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        stmt = select(
            summary_subquery.c.batch_id,
            summary_subquery.c.executed_at,
            summary_subquery.c.total_count,
            summary_subquery.c.success_count,
            summary_subquery.c.failed_count,
        )
        stmt = self._apply_executed_at_filters(stmt, summary_subquery, start_dt, end_dt)
        stmt = stmt.order_by(summary_subquery.c.executed_at.desc()).offset(offset).limit(page_size)

        result = await self.session.execute(stmt)
        rows = result.all()

        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "batch_id": row.batch_id,
                    "executed_at": safe_isoformat(row.executed_at),
                    total_key: int(row.total_count or 0),
                    "success_count": int(row.success_count or 0),
                    "failed_count": int(row.failed_count or 0),
                }
            )

        return items, total

    async def _get_batch_detail(
        self,
        *,
        model: Any,
        batch_id: str,
        total_key: str,
        detail_key: str,
        detail_column: Any,
        extra_columns: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """统一查询批次详情，只提取页面实际需要的字段。"""
        summary_stmt = select(
            func.min(model.created_at).label("executed_at"),
            func.count().label("total_count"),
            func.sum(case((model.status == "success", 1), else_=0)).label("success_count"),
            func.sum(case((model.status == "failed", 1), else_=0)).label("failed_count"),
        ).where(model.batch_id == batch_id)

        summary_result = await self.session.execute(summary_stmt)
        summary = summary_result.first()
        if not summary or not summary.total_count:
            return None

        extra_columns = extra_columns or {}
        selected_columns = [
            model.id.label("id"),
            model.batch_id.label("batch_id"),
            model.account_id.label("account_id"),
            detail_column.label(detail_key),
            model.status.label("status"),
            model.error_message.label("error_message"),
            model.created_at.label("created_at"),
        ]
        selected_columns.extend(
            column.label(key) for key, column in extra_columns.items()
        )
        logs_stmt = (
            select(*selected_columns)
            .where(model.batch_id == batch_id)
            .order_by(model.created_at.asc())
        )

        logs_result = await self.session.execute(logs_stmt)
        logs_rows = logs_result.all()

        logs: list[dict[str, Any]] = []
        for row in logs_rows:
            log_data = {
                "id": row.id,
                "batch_id": row.batch_id,
                "account_id": row.account_id,
                detail_key: getattr(row, detail_key),
                "status": row.status,
                "error_message": row.error_message,
                "created_at": safe_isoformat(row.created_at),
            }
            for key in extra_columns:
                value = getattr(row, key)
                log_data[key] = safe_isoformat(value) if isinstance(value, datetime) else value
            logs.append(log_data)

        return {
            "batch_id": batch_id,
            "executed_at": safe_isoformat(summary.executed_at),
            total_key: int(summary.total_count or 0),
            "success_count": int(summary.success_count or 0),
            "failed_count": int(summary.failed_count or 0),
            "logs": logs,
        }

    async def list_redelivery_batches(
        self,
        *,
        start_date: str | None,
        end_date: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """分页查询补发货批次列表。"""
        return await self._list_batches(
            model=ScheduledRedeliveryLog,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            total_key="total_orders",
        )

    async def get_redelivery_batch_detail(self, batch_id: str) -> dict[str, Any] | None:
        """查询补发货批次详情。"""
        return await self._get_batch_detail(
            model=ScheduledRedeliveryLog,
            batch_id=batch_id,
            total_key="total_orders",
            detail_key="order_no",
            detail_column=ScheduledRedeliveryLog.order_no,
        )

    async def list_token_renewal_batches(
        self,
        *,
        start_date: str | None,
        end_date: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """分页查询 Token 续期批次列表。"""
        return await self._list_batches(
            model=ScheduledTokenRenewalLog,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            total_key="total_accounts",
        )

    async def get_token_renewal_batch_detail(
        self,
        batch_id: str,
    ) -> dict[str, Any] | None:
        """查询 Token 续期批次详情。"""
        return await self._get_batch_detail(
            model=ScheduledTokenRenewalLog,
            batch_id=batch_id,
            total_key="total_accounts",
            detail_key="token_user_id",
            detail_column=ScheduledTokenRenewalLog.token_user_id,
            extra_columns={
                "renew_expire_at": ScheduledTokenRenewalLog.renew_expire_at,
            },
        )

    async def list_rate_batches(
        self,
        *,
        start_date: str | None,
        end_date: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """分页查询补评价批次列表。"""
        return await self._list_batches(
            model=ScheduledRateLog,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            total_key="total_orders",
        )

    async def get_rate_batch_detail(self, batch_id: str) -> dict[str, Any] | None:
        """查询补评价批次详情。"""
        return await self._get_batch_detail(
            model=ScheduledRateLog,
            batch_id=batch_id,
            total_key="total_orders",
            detail_key="order_no",
            detail_column=ScheduledRateLog.order_no,
        )

    async def list_polish_batches(
        self,
        *,
        start_date: str | None,
        end_date: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """分页查询擦亮批次列表。"""
        return await self._list_batches(
            model=ScheduledPolishLog,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            total_key="total_items",
        )

    async def get_polish_batch_detail(self, batch_id: str) -> dict[str, Any] | None:
        """查询擦亮批次详情。"""
        return await self._get_batch_detail(
            model=ScheduledPolishLog,
            batch_id=batch_id,
            total_key="total_items",
            detail_key="item_id",
            detail_column=ScheduledPolishLog.item_id,
        )

    async def list_red_flower_batches(
        self,
        *,
        start_date: str | None,
        end_date: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """分页查询求小红花批次列表。"""
        return await self._list_batches(
            model=ScheduledRedFlowerLog,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            total_key="total_orders",
        )

    async def get_red_flower_batch_detail(self, batch_id: str) -> dict[str, Any] | None:
        """查询求小红花批次详情。"""
        return await self._get_batch_detail(
            model=ScheduledRedFlowerLog,
            batch_id=batch_id,
            total_key="total_orders",
            detail_key="order_no",
            detail_column=ScheduledRedFlowerLog.order_no,
        )
