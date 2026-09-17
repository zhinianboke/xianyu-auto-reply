"""
仪表盘统计服务。

功能：
1. 统一普通用户与管理员仪表盘统计查询。
2. 减少重复 count、Python 层统计和多次扫描同一张表的开销。
3. 在不改变接口返回格式的前提下优化首页统计速度。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.services.auto_reply_stats_service import AutoReplyStatsService
from app.services.dashboard_stats_cache_service import DashboardStatsCacheService
from common.models.agent_order import AgentOrder
from common.models.card import Card
from common.models.user import User
from common.models.xy_account import XYAccount
from common.models.xy_keyword_rule import XYKeywordRule
from common.models.xy_order import XYOrder
from common.services.account_limit_service import AccountLimitService

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))


class DashboardStatsService:
    """仪表盘统计聚合服务。"""

    # Online cookies cache: (timestamp, count)
    _online_cookies_cache: tuple[float, int] | None = None
    _ONLINE_COOKIES_CACHE_TTL = 10  # seconds

    # Online account-id set cache: (timestamp, frozenset[account_id])
    _online_ids_cache: tuple[float, frozenset[str]] | None = None
    _ONLINE_IDS_CACHE_TTL = 10  # seconds

    INACTIVE_ACCOUNT_STATUSES = ("inactive", "disabled", "suspended", "deleted")
    # 已关闭/已退款订单：不计入营收、有效订单与待处理统计
    CLOSED_ORDER_STATUSES = ("cancelled", "已关闭", "refunded", "退款成功", "已退款")
    SHIPPED_ORDER_STATUSES = ("shipped", "completed", "已发货", "已完成")
    PENDING_EXCLUDED_ORDER_STATUSES = (*CLOSED_ORDER_STATUSES, *SHIPPED_ORDER_STATUSES)

    def __init__(self, session: AsyncSession):
        self.session = session

    @classmethod
    def _build_today_start(cls) -> datetime:
        return datetime.now(BEIJING_TZ).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
            tzinfo=None,
        )

    @classmethod
    def _build_enabled_account_condition(cls):
        return or_(
            XYAccount.status.is_(None),
            XYAccount.status == "",
            XYAccount.status.notin_(cls.INACTIVE_ACCOUNT_STATUSES),
        )

    @classmethod
    def _merge_trend_rows(cls, rows, amount_map: dict[str, float], count_map: dict[str, int]) -> None:
        for row in rows:
            date_str = row.order_date.strftime("%m-%d") if hasattr(row.order_date, "strftime") else str(row.order_date)
            amount_map[date_str] = round(amount_map.get(date_str, 0) + float(row.daily_amount or 0), 2)
            count_map[date_str] = count_map.get(date_str, 0) + int(row.daily_count or 0)

    @classmethod
    def _merge_order_summary_row(cls, summary: dict[str, int | float], row) -> None:
        summary["today_orders"] = int(summary["today_orders"]) + int(row.today_orders or 0)
        summary["today_shipped"] = int(summary["today_shipped"]) + int(row.today_shipped or 0)
        summary["today_pending"] = int(summary["today_pending"]) + int(row.today_pending or 0)
        summary["today_amount"] = float(summary["today_amount"]) + float(row.today_amount or 0)

    async def _get_today_order_summary_row(self, *, time_column, start_time: datetime):
        stmt = (
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (XYOrder.status.notin_(self.CLOSED_ORDER_STATUSES), 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("today_orders"),
                func.coalesce(
                    func.sum(
                        case(
                            (XYOrder.status.in_(self.SHIPPED_ORDER_STATUSES), 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("today_shipped"),
                func.coalesce(
                    func.sum(
                        case(
                            (XYOrder.status.notin_(self.PENDING_EXCLUDED_ORDER_STATUSES), 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("today_pending"),
                func.coalesce(
                    func.sum(
                        case(
                            (XYOrder.status.notin_(self.CLOSED_ORDER_STATUSES), XYOrder.amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("today_amount"),
            )
            .select_from(XYOrder)
            .where(time_column >= start_time)
        )
        return (await self.session.execute(stmt)).one()

    async def _get_limit_status(self, owner_id: int) -> dict[str, int | None]:
        return await DashboardStatsCacheService.get_user_limit_status(
            owner_id,
            lambda: AccountLimitService(self.session).get_status(owner_id),
        )

    async def _load_admin_dashboard_bundle(self) -> dict[str, dict[str, int | float]]:
        today_start = self._build_today_start()

        users_stmt = select(func.count()).select_from(User)
        total_users = int((await self.session.execute(users_stmt)).scalar() or 0)

        accounts_stmt = select(
            func.count().label("total_accounts"),
            func.coalesce(
                func.sum(
                    case(
                        (self._build_enabled_account_condition(), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("active_accounts"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                XYAccount.login_password.isnot(None),
                                XYAccount.login_password != "",
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("password_configured"),
        ).select_from(XYAccount)
        accounts_row = (await self.session.execute(accounts_stmt)).one()

        keywords_stmt = select(func.count()).select_from(XYKeywordRule)
        total_keywords = int((await self.session.execute(keywords_stmt)).scalar() or 0)

        orders_stmt = select(
            func.coalesce(
                func.sum(
                    case(
                        (XYOrder.status.notin_(self.CLOSED_ORDER_STATUSES), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("total_orders"),
        ).select_from(XYOrder)
        orders_row = (await self.session.execute(orders_stmt)).one()

        cards_stmt = select(func.count()).select_from(Card)
        total_cards = int((await self.session.execute(cards_stmt)).scalar() or 0)

        reply_stats = await AutoReplyStatsService(self.session).get_today_and_yesterday_success_reply_counts()

        today_users_stmt = select(func.count()).select_from(User).where(User.created_at >= today_start)
        today_users = int((await self.session.execute(today_users_stmt)).scalar() or 0)

        today_accounts_stmt = select(func.count()).select_from(XYAccount).where(XYAccount.created_at >= today_start)
        today_accounts = int((await self.session.execute(today_accounts_stmt)).scalar() or 0)

        today_order_summary: dict[str, int | float] = {
            "today_orders": 0,
            "today_shipped": 0,
            "today_pending": 0,
            "today_amount": 0.0,
        }
        # 只按真实下单时间(placed_at)统计，不对 created_at 做回退，
        # 避免同步历史订单时 created_at=今天被误算为今日订单
        placed_row = await self._get_today_order_summary_row(time_column=XYOrder.placed_at, start_time=today_start)
        self._merge_order_summary_row(today_order_summary, placed_row)

        today_agent_orders_stmt = select(func.count()).select_from(AgentOrder).where(AgentOrder.created_at >= today_start)
        today_agent_orders = int((await self.session.execute(today_agent_orders_stmt)).scalar() or 0)

        return {
            "admin_stats": {
                "total_users": total_users,
                "total_cookies": int(accounts_row.total_accounts or 0),
                "active_cookies": int(accounts_row.active_accounts or 0),
                "total_keywords": total_keywords,
                "total_orders": int(orders_row.total_orders or 0),
                "today_reply_count": int(reply_stats["today_reply_count"]),
                "yesterday_reply_count": int(reply_stats["yesterday_reply_count"]),
                "total_cards": total_cards,
                "password_configured": int(accounts_row.password_configured or 0),
            },
            "today_stats": {
                "today_users": today_users,
                "today_accounts": today_accounts,
                "today_orders": int(today_order_summary["today_orders"]),
                "today_shipped": int(today_order_summary["today_shipped"]),
                "today_pending": int(today_order_summary["today_pending"]),
                "today_amount": round(float(today_order_summary["today_amount"]), 2),
                "today_agent_orders": today_agent_orders,
            },
        }

    async def _get_admin_dashboard_bundle(self) -> dict[str, dict[str, int | float]]:
        return await DashboardStatsCacheService.get_admin_bundle(self._load_admin_dashboard_bundle)

    async def get_account_dashboard_stats(
        self,
        *,
        current_user_id: int,
        account_scope_owner_id: int | None,
        reply_scope_owner_id: int | None,
    ) -> dict[str, int | None]:
        """获取首页基础统计。"""
        account_stmt = select(
            func.count().label("total_accounts"),
            func.coalesce(
                func.sum(
                    case(
                        (self._build_enabled_account_condition(), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("active_accounts"),
        ).select_from(XYAccount)
        if account_scope_owner_id is not None:
            account_stmt = account_stmt.where(XYAccount.owner_id == account_scope_owner_id)
        account_row = (await self.session.execute(account_stmt)).one()

        keyword_stmt = (
            select(func.count())
            .select_from(XYKeywordRule)
            .join(XYAccount, XYKeywordRule.account_pk == XYAccount.id)
            .where(XYKeywordRule.is_active.is_(True))
        )
        if account_scope_owner_id is not None:
            keyword_stmt = keyword_stmt.where(XYAccount.owner_id == account_scope_owner_id)
        total_keywords = int((await self.session.execute(keyword_stmt)).scalar() or 0)

        order_stmt = select(func.count()).select_from(XYOrder)
        if account_scope_owner_id is not None:
            order_stmt = order_stmt.where(XYOrder.owner_id == account_scope_owner_id)
        total_orders = int((await self.session.execute(order_stmt)).scalar() or 0)

        limit_status = await self._get_limit_status(current_user_id)
        reply_stats = await AutoReplyStatsService(self.session).get_today_and_yesterday_success_reply_counts(
            reply_scope_owner_id
        )

        return {
            "total_accounts": int(account_row.total_accounts or 0),
            "active_accounts": int(account_row.active_accounts or 0),
            "total_keywords": total_keywords,
            "total_orders": total_orders,
            "today_reply_count": int(reply_stats["today_reply_count"]),
            "yesterday_reply_count": int(reply_stats["yesterday_reply_count"]),
            "account_limit": limit_status["account_limit"],
            "used_account_count": int(limit_status["used_count"]),
            "remaining_account_count": limit_status["remaining_count"],
        }

    async def _get_online_cookies_count(self) -> int:
        """实时获取真实 WebSocket 在线账号数（10 秒 TTL 缓存）。

        失败时返回 0，不影响其它统计展示。
        """
        now = time.time()
        if self.__class__._online_cookies_cache is not None:
            ts, count = self.__class__._online_cookies_cache
            if now - ts < self._ONLINE_COOKIES_CACHE_TTL:
                return count

        try:
            settings = get_settings()
            url = f"{settings.websocket_service_url.rstrip('/')}/internal/accounts/connection-stats"
            response = await get_http_client().get(url)
            if isinstance(response, dict) and response.get("success"):
                count = int((response.get("data") or {}).get("connected", 0) or 0)
                self.__class__._online_cookies_cache = (now, count)
                return count
        except Exception as e:
            logger.warning(f"获取在线账号数失败: {e}")
        return 0

    async def get_online_account_ids(self) -> frozenset[str]:
        """实时获取真实 WebSocket 在线账号 ID 集合（10 秒 TTL 缓存）。

        口径与仪表盘“在线账号”一致：取 websocket 服务 connection-stats 的
        connected_account_ids（真正建立 WebSocket 连接的账号）。失败返回空集合。
        """
        now = time.time()
        if self.__class__._online_ids_cache is not None:
            ts, ids = self.__class__._online_ids_cache
            if now - ts < self._ONLINE_IDS_CACHE_TTL:
                return ids

        try:
            settings = get_settings()
            url = f"{settings.websocket_service_url.rstrip('/')}/internal/accounts/connection-stats"
            # 加 3 秒超时上限：websocket 慢/不可达时也不会拖慢账号列表（最多等 3 秒即按离线处理）
            response = await asyncio.wait_for(get_http_client().get(url), timeout=3.0)
            if isinstance(response, dict) and response.get("success"):
                raw_ids = (response.get("data") or {}).get("connected_account_ids") or []
                ids = frozenset(str(x) for x in raw_ids)
                self.__class__._online_ids_cache = (now, ids)
                return ids
        except Exception as e:
            logger.warning(f"获取在线账号ID列表失败: {e}")
        # 失败也缓存（空集合，10 秒）：避免 websocket 异常时每次账号列表请求都重试拖慢响应
        self.__class__._online_ids_cache = (now, frozenset())
        return frozenset()

    async def get_admin_dashboard_stats(self, *, current_user_id: int) -> dict[str, int | None]:
        """获取管理员首页全局统计。"""
        bundle = await self._get_admin_dashboard_bundle()
        limit_status = await self._get_limit_status(current_user_id)
        admin_stats = bundle["admin_stats"]
        online_cookies = await self._get_online_cookies_count()

        return {
            "total_users": int(admin_stats["total_users"]),
            "total_cookies": int(admin_stats["total_cookies"]),
            "active_cookies": int(admin_stats["active_cookies"]),
            "online_cookies": online_cookies,
            "total_keywords": int(admin_stats["total_keywords"]),
            "total_orders": int(admin_stats["total_orders"]),
            "today_reply_count": int(admin_stats["today_reply_count"]),
            "yesterday_reply_count": int(admin_stats["yesterday_reply_count"]),
            "total_cards": int(admin_stats["total_cards"]),
            "password_configured": int(admin_stats["password_configured"]),
            "current_user_account_limit": limit_status["account_limit"],
            "current_user_used_account_count": int(limit_status["used_count"]),
            "current_user_remaining_account_count": limit_status["remaining_count"],
        }

    async def get_admin_today_stats(self) -> dict[str, int | float]:
        """获取管理员今日统计。"""
        bundle = await self._get_admin_dashboard_bundle()
        today_stats = bundle["today_stats"]

        return {
            "today_users": int(today_stats["today_users"]),
            "today_accounts": int(today_stats["today_accounts"]),
            "today_orders": int(today_stats["today_orders"]),
            "today_shipped": int(today_stats["today_shipped"]),
            "today_pending": int(today_stats["today_pending"]),
            "today_amount": round(float(today_stats["today_amount"]), 2),
            "today_agent_orders": int(today_stats["today_agent_orders"]),
        }

    async def get_order_amount_trend(self, *, owner_id: int | None, days: int = 30) -> list[dict[str, int | float | str]]:
        """获取近N天订单金额趋势。"""
        start_date = self._build_today_start() - timedelta(days=days - 1)

        # 只按真实下单时间(placed_at)统计趋势，不对 created_at 做回退，
        # 避免同步历史订单时 created_at=今天被误算到今日曲线
        placed_stmt = (
            select(
                func.date(XYOrder.placed_at).label("order_date"),
                func.coalesce(func.sum(XYOrder.amount), 0).label("daily_amount"),
                func.count().label("daily_count"),
            )
            .select_from(XYOrder)
            .where(
                XYOrder.placed_at >= start_date,
                XYOrder.status.notin_(self.CLOSED_ORDER_STATUSES),
            )
            .group_by(func.date(XYOrder.placed_at))
            .order_by(func.date(XYOrder.placed_at))
        )
        if owner_id is not None:
            placed_stmt = placed_stmt.where(XYOrder.owner_id == owner_id)

        placed_rows = (await self.session.execute(placed_stmt)).all()

        amount_map: dict[str, float] = {}
        count_map: dict[str, int] = {}
        self._merge_trend_rows(placed_rows, amount_map, count_map)

        trend_data: list[dict[str, int | float | str]] = []
        for index in range(days):
            current_day = start_date + timedelta(days=index)
            date_key = current_day.strftime("%m-%d")
            trend_data.append(
                {
                    "date": date_key,
                    "amount": round(amount_map.get(date_key, 0), 2),
                    "count": count_map.get(date_key, 0),
                }
            )
        return trend_data
