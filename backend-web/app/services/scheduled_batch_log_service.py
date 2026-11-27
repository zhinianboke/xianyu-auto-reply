"""
定时批次日志查询服务。

功能：
1. 统一补发货日志、补评价日志、擦亮日志的批次列表查询。
2. 先分页查询批次，再统计当前页批次的执行结果。
3. 提供批次详情查询，减少 ORM 实体加载开销。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.scheduled_polish_log import ScheduledPolishLog
from common.models.scheduled_rate_log import ScheduledRateLog
from common.models.scheduled_red_flower_log import ScheduledRedFlowerLog
from common.models.scheduled_redelivery_log import ScheduledRedeliveryLog
from common.models.scheduled_token_renewal_log import ScheduledTokenRenewalLog
from common.utils.date_filters import date_filter_bounds
from common.utils.time_utils import safe_isoformat


class ScheduledBatchLogService:
    """统一处理定时批次日志的列表与详情查询。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _parse_start_date(value: str | None) -> datetime | None:
        """复用公共日期边界；开始日期取当天零点，非法参数明确报错。"""
        return date_filter_bounds(value, None)[0]

    @staticmethod
    def _parse_end_date(value: str | None) -> datetime | None:
        """复用公共日期边界；结束日期取次日零点，非法参数明确报错。"""
        return date_filter_bounds(None, value)[1]

    @staticmethod
    def _build_batch_times_query(
        *,
        model: Any,
        start_dt: datetime | None,
        end_dt: datetime | None,
    ):
        """从日期范围内找候选批次，返回全批首次执行时间落在该范围内的批次。"""
        stmt = select(
            model.batch_id.label("batch_id"),
            func.min(model.created_at).label("executed_at"),
        ).group_by(model.batch_id)
        if start_dt is not None:
            stmt = stmt.where(model.created_at >= start_dt)
        if end_dt is not None:
            stmt = stmt.where(model.created_at < end_dt)
        if start_dt is None:
            return stmt

        # 已在开始日期前执行的批次，即使区间内还有记录，也不属于查询结果。
        candidates = stmt.subquery()
        earlier_log = select(1).where(
            model.batch_id == candidates.c.batch_id,
            model.created_at < start_dt,
        ).exists()
        return select(candidates.c.batch_id, candidates.c.executed_at).where(~earlier_log)

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
        start_dt, end_dt = date_filter_bounds(start_date, end_date)
        offset = (page - 1) * page_size

        batch_times = self._build_batch_times_query(
            model=model,
            start_dt=start_dt,
            end_dt=end_dt,
        )
        if start_dt is None and end_dt is None:
            count_stmt = select(func.count(func.distinct(model.batch_id)))
        else:
            count_stmt = select(func.count()).select_from(batch_times.subquery())
        total = int((await self.session.scalar(count_stmt)) or 0)
        if offset >= total:
            return [], total

        batch_time_columns = batch_times.selected_columns
        page_batches = (
            batch_times
            .order_by(batch_time_columns.executed_at.desc(), batch_time_columns.batch_id.desc())
            .offset(offset)
            .limit(page_size)
            .subquery()
        )

        stmt = (
            select(
                page_batches.c.batch_id,
                page_batches.c.executed_at,
                func.count().label("total_count"),
                func.sum(case((model.status == "success", 1), else_=0)).label("success_count"),
                func.sum(case((model.status == "failed", 1), else_=0)).label("failed_count"),
            )
            .select_from(page_batches)
            .join(model, model.batch_id == page_batches.c.batch_id)
            .group_by(page_batches.c.batch_id, page_batches.c.executed_at)
            .order_by(page_batches.c.executed_at.desc(), page_batches.c.batch_id.desc())
        )

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
