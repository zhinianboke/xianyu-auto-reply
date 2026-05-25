"""
自动回复统计服务

功能：
1. 统一自动回复成功日志的统计口径
2. 提供今日自动回复成功总数统计
3. 提供按账号聚合的今日自动回复成功统计
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.auto_reply_message_log import XYAutoReplyMessageLog

BEIJING_TZ = timezone(timedelta(hours=8))


class AutoReplyStatsService:
    """自动回复统计服务"""

    SUCCESS_REPLY_STRATEGIES = ("keyword", "ai")
    DEFAULT_REPLY_SCOPES = ("item", "account")

    def __init__(self, session: AsyncSession):
        self.session = session

    @classmethod
    def _build_success_reply_scope_condition(cls):
        return or_(
            XYAutoReplyMessageLog.reply_strategy.in_(list(cls.SUCCESS_REPLY_STRATEGIES)),
            and_(
                XYAutoReplyMessageLog.reply_strategy == "default",
                XYAutoReplyMessageLog.default_reply_scope.in_(list(cls.DEFAULT_REPLY_SCOPES)),
            ),
        )

    @classmethod
    def _build_base_success_conditions(
        cls,
        *,
        owner_id: int | None = None,
        account_ids: Iterable[str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list:
        conditions = [XYAutoReplyMessageLog.process_status == "success"]
        if owner_id is not None:
            conditions.append(XYAutoReplyMessageLog.owner_id == owner_id)

        normalized_account_ids = cls._normalize_account_ids(account_ids)
        if normalized_account_ids:
            conditions.append(XYAutoReplyMessageLog.account_id.in_(normalized_account_ids))

        if start_time is not None:
            conditions.append(XYAutoReplyMessageLog.created_at >= start_time)
        if end_time is not None:
            conditions.append(XYAutoReplyMessageLog.created_at < end_time)
        return conditions

    @classmethod
    def build_success_reply_branch_conditions(
        cls,
        *,
        owner_id: int | None = None,
        account_ids: Iterable[str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> tuple[list, list]:
        base_conditions = cls._build_base_success_conditions(
            owner_id=owner_id,
            account_ids=account_ids,
            start_time=start_time,
            end_time=end_time,
        )
        strategy_conditions = [
            *base_conditions,
            XYAutoReplyMessageLog.reply_strategy.in_(list(cls.SUCCESS_REPLY_STRATEGIES)),
        ]
        default_conditions = [
            *base_conditions,
            XYAutoReplyMessageLog.reply_strategy == "default",
            XYAutoReplyMessageLog.default_reply_scope.in_(list(cls.DEFAULT_REPLY_SCOPES)),
        ]
        return strategy_conditions, default_conditions

    @classmethod
    def _normalize_account_ids(cls, account_ids: Iterable[str] | None) -> list[str]:
        if not account_ids:
            return []
        return list(
            dict.fromkeys(
                account_id.strip()
                for account_id in account_ids
                if account_id and account_id.strip()
            )
        )

    @classmethod
    def build_success_reply_conditions(
        cls,
        *,
        owner_id: int | None = None,
        account_ids: Iterable[str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list:
        conditions = cls._build_base_success_conditions(
            owner_id=owner_id,
            account_ids=account_ids,
            start_time=start_time,
            end_time=end_time,
        )
        conditions.append(cls._build_success_reply_scope_condition())
        return conditions

    def _get_day_range(self, day_offset: int = 0) -> tuple[datetime, datetime]:
        day_start = datetime.now(BEIJING_TZ).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ) + timedelta(days=day_offset)
        day_end = day_start + timedelta(days=1)
        return day_start.replace(tzinfo=None), day_end.replace(tzinfo=None)

    def _build_success_reply_conditions(self, day_offset: int = 0) -> list:
        day_start, day_end = self._get_day_range(day_offset)
        return self.build_success_reply_conditions(start_time=day_start, end_time=day_end)

    async def _count_by_condition_groups(self, condition_groups: tuple[list, ...]) -> int:
        total = 0
        for conditions in condition_groups:
            stmt = select(func.count()).select_from(XYAutoReplyMessageLog).where(*conditions)
            result = await self.session.execute(stmt)
            total += int(result.scalar() or 0)
        return total

    async def get_success_reply_count(self, day_offset: int = 0, owner_id: int | None = None) -> int:
        day_start, day_end = self._get_day_range(day_offset)
        return await self._count_by_condition_groups(
            self.build_success_reply_branch_conditions(
                owner_id=owner_id,
                start_time=day_start,
                end_time=day_end,
            )
        )

    async def get_today_and_yesterday_success_reply_counts(self, owner_id: int | None = None) -> dict[str, int]:
        yesterday_start, yesterday_end = self._get_day_range(-1)
        today_start, today_end = self._get_day_range(0)

        condition_groups = self.build_success_reply_branch_conditions(
            owner_id=owner_id,
            start_time=yesterday_start,
            end_time=today_end,
        )

        today_reply_count = 0
        yesterday_reply_count = 0
        for conditions in condition_groups:
            stmt = select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    XYAutoReplyMessageLog.created_at >= today_start,
                                    XYAutoReplyMessageLog.created_at < today_end,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("today_reply_count"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    XYAutoReplyMessageLog.created_at >= yesterday_start,
                                    XYAutoReplyMessageLog.created_at < yesterday_end,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("yesterday_reply_count"),
            ).select_from(XYAutoReplyMessageLog).where(*conditions)
            row = (await self.session.execute(stmt)).one()
            today_reply_count += int(row.today_reply_count or 0)
            yesterday_reply_count += int(row.yesterday_reply_count or 0)

        return {
            "today_reply_count": today_reply_count,
            "yesterday_reply_count": yesterday_reply_count,
        }

    async def get_today_success_reply_count(self, owner_id: int | None = None) -> int:
        """获取今日自动回复成功总数"""
        return await self.get_success_reply_count(day_offset=0, owner_id=owner_id)

    async def get_yesterday_success_reply_count(self, owner_id: int | None = None) -> int:
        return await self.get_success_reply_count(day_offset=-1, owner_id=owner_id)

    async def get_success_reply_counts_by_account(self, account_ids: Iterable[str], day_offset: int = 0) -> dict[str, int]:
        normalized_account_ids = self._normalize_account_ids(account_ids)
        if not normalized_account_ids:
            return {}

        day_start, day_end = self._get_day_range(day_offset)
        condition_groups = self.build_success_reply_branch_conditions(
            account_ids=normalized_account_ids,
            start_time=day_start,
            end_time=day_end,
        )

        counts_by_account: dict[str, int] = {}
        for conditions in condition_groups:
            stmt = (
                select(
                    XYAutoReplyMessageLog.account_id,
                    func.count().label("count"),
                )
                .where(*conditions)
                .group_by(XYAutoReplyMessageLog.account_id)
            )
            result = await self.session.execute(stmt)
            for row in result.fetchall():
                account_id = str(row.account_id)
                counts_by_account[account_id] = counts_by_account.get(account_id, 0) + int(row.count or 0)
        return counts_by_account

    async def get_today_success_reply_counts_by_account(self, account_ids: Iterable[str]) -> dict[str, int]:
        """按账号获取今日自动回复成功数"""
        return await self.get_success_reply_counts_by_account(account_ids=account_ids, day_offset=0)
