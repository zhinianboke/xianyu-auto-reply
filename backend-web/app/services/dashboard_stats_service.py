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
from datetime import datetime, timedelta

from sqlalchemy import and_, case, func, null, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.services.auto_reply_stats_service import AutoReplyStatsService
from app.services.dashboard_stats_cache_service import DashboardStatsCacheService
from app.services.dashboard_totals_service import build_dashboard_user_count
from common.models.agent_order import AgentOrder
from common.models.card import Card
from common.models.user import User
from common.models.xy_account import XYAccount
from common.models.xy_keyword_rule import XYKeywordRule
from common.models.xy_order import XYOrder
from common.services.account_limit_service import AccountLimitService
from common.db.query_conditions import not_deleted
from common.utils.date_filters import next_day_start
from common.utils.time_utils import get_beijing_now_naive

logger = logging.getLogger(__name__)

class DashboardStatsService:
    """仪表盘统计聚合服务。"""

    # 在线账号数缓存和当前共享的 HTTP 查询，不持有数据库会话。
    _online_cookies_cache: tuple[float, int] | None = None
    _online_cookies_task: asyncio.Task[int | None] | None = None
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
        """返回当前北京时间所在日期的零点，与数据库时间列比较。"""
        return get_beijing_now_naive().replace(hour=0, minute=0, second=0, microsecond=0)

    @classmethod
    def _build_enabled_account_condition(cls):
        return or_(
            XYAccount.status.is_(None),
            XYAccount.status == "",
            XYAccount.status.notin_(cls.INACTIVE_ACCOUNT_STATUSES),
        )

    @classmethod
    def _build_account_totals_statement(cls):
        """构建账号总数与启用账号数查询，可按所属用户筛选。"""
        return select(
            func.count().label("total_accounts"),
            func.coalesce(func.sum(case((cls._build_enabled_account_condition(), 1), else_=0)), 0)
            .label("active_accounts"),
        ).select_from(XYAccount)

    async def _get_today_order_summary_row(self, today_start: datetime, today_end: datetime):
        """按真实下单时间聚合一天内的订单数、状态和金额。"""
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
            .where(XYOrder.placed_at >= today_start, XYOrder.placed_at < today_end)
        )
        return (await self.session.execute(stmt)).one()

    async def _get_limit_status(self, owner_id: int) -> dict[str, int | None]:
        return await DashboardStatsCacheService.get_user_limit_status(
            owner_id,
            lambda: AccountLimitService(self.session).get_status(owner_id),
        )

    async def _load_global_totals(self) -> dict[str, int]:
        """同一扫描计算全局账号、关键词和订单的两种展示口径。"""
        accounts_stmt = self._build_account_totals_statement().add_columns(
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
        )
        accounts_row = (await self.session.execute(accounts_stmt)).one()

        # 两个统计接口的关键词口径不同：全量规则与关联真实账号的启用规则。
        keywords_stmt = select(
            func.count().label("total_keywords"),
            func.coalesce(func.sum(case(
                (and_(XYKeywordRule.is_active.is_(True), XYAccount.id.isnot(None)), 1),
                else_=0,
            )), 0).label("active_keywords"),
        ).select_from(XYKeywordRule).outerjoin(XYAccount, XYKeywordRule.account_pk == XYAccount.id)
        keywords_row = (await self.session.execute(keywords_stmt)).one()

        orders_stmt = select(
            func.count().label("all_orders"),
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

        return {
            "total_accounts": int(accounts_row.total_accounts or 0),
            "active_accounts": int(accounts_row.active_accounts or 0),
            "password_configured": int(accounts_row.password_configured or 0),
            "total_keywords": int(keywords_row.total_keywords or 0),
            "active_keywords": int(keywords_row.active_keywords or 0),
            "total_orders": int(orders_row.all_orders or 0),
            "valid_orders": int(orders_row.total_orders or 0),
        }

    async def _get_global_totals(self) -> dict[str, int]:
        """复用基础统计与管理员统计所需的全局总数快照。"""
        return await DashboardStatsCacheService.get_snapshot("global_totals", self._load_global_totals)

    async def _load_admin_overview(self, today_start: datetime) -> dict[str, int]:
        """读取全局用户、卡券和指定北京时间日期的回复数。"""
        cards_stmt = select(func.count()).select_from(Card).where(not_deleted(Card))
        total_cards = int((await self.session.execute(cards_stmt)).scalar() or 0)
        total_users = int((await self.session.execute(build_dashboard_user_count())).scalar() or 0)
        reply_stats = await AutoReplyStatsService(self.session).get_today_and_yesterday_success_reply_counts(
            today_start=today_start,
        )
        return {**reply_stats, "total_users": total_users, "total_cards": total_cards}

    async def _load_admin_today(self, today_start: datetime) -> dict[str, int | float]:
        """读取指定北京时间日期内新增的用户、账号和订单统计。"""
        today_end = next_day_start(today_start)
        users_stmt = build_dashboard_user_count().where(
            User.created_at >= today_start, User.created_at < today_end,
        )
        today_users = int((await self.session.execute(users_stmt)).scalar() or 0)

        today_accounts_stmt = select(func.count()).select_from(XYAccount).where(
            XYAccount.created_at >= today_start, XYAccount.created_at < today_end,
        )
        today_accounts = int((await self.session.execute(today_accounts_stmt)).scalar() or 0)

        # 只按真实下单时间(placed_at)统计，不对 created_at 做回退，
        # 避免同步历史订单时 created_at=今天被误算为今日订单
        placed_row = await self._get_today_order_summary_row(today_start, today_end)

        today_agent_orders_stmt = select(func.count()).select_from(AgentOrder).where(
            AgentOrder.created_at >= today_start, AgentOrder.created_at < today_end,
        )
        today_agent_orders = int((await self.session.execute(today_agent_orders_stmt)).scalar() or 0)

        return {
            "today_users": today_users,
            "today_accounts": today_accounts,
            "today_orders": int(placed_row.today_orders or 0),
            "today_shipped": int(placed_row.today_shipped or 0),
            "today_pending": int(placed_row.today_pending or 0),
            "today_amount": round(float(placed_row.today_amount or 0), 2),
            "today_agent_orders": today_agent_orders,
        }

    async def _load_owner_account_totals(self, owner_id: int) -> dict[str, int]:
        """按所属用户统计账号、关联账号的启用关键词及订单。"""
        account_stmt = self._build_account_totals_statement().where(XYAccount.owner_id == owner_id)
        account_row = (await self.session.execute(account_stmt)).one()
        keywords_stmt = (
            select(func.count())
            .select_from(XYKeywordRule)
            .join(XYAccount, XYKeywordRule.account_pk == XYAccount.id)
            .where(XYKeywordRule.is_active.is_(True), XYAccount.owner_id == owner_id)
        )
        orders_stmt = select(func.count()).select_from(XYOrder).where(XYOrder.owner_id == owner_id)
        return {
            "total_accounts": int(account_row.total_accounts or 0),
            "active_accounts": int(account_row.active_accounts or 0),
            "total_keywords": int((await self.session.execute(keywords_stmt)).scalar() or 0),
            "total_orders": int((await self.session.execute(orders_stmt)).scalar() or 0),
        }

    async def get_account_dashboard_stats(
        self,
        *,
        current_user_id: int,
        account_scope_owner_id: int | None,
        reply_scope_owner_id: int | None,
    ) -> dict[str, int | None]:
        """获取首页基础统计。"""
        if account_scope_owner_id is None:
            global_totals = await self._get_global_totals()
            totals = {
                "total_accounts": global_totals["total_accounts"],
                "active_accounts": global_totals["active_accounts"],
                "total_keywords": global_totals["active_keywords"],
                "total_orders": global_totals["total_orders"],
            }
        else:
            totals = await self._load_owner_account_totals(account_scope_owner_id)

        limit_status = await self._get_limit_status(current_user_id)
        reply_stats = await AutoReplyStatsService(self.session).get_today_and_yesterday_success_reply_counts(
            reply_scope_owner_id
        )

        return {
            **totals,
            "today_reply_count": int(reply_stats["today_reply_count"]),
            "yesterday_reply_count": int(reply_stats["yesterday_reply_count"]),
            "account_limit": limit_status["account_limit"],
            "used_account_count": int(limit_status["used_count"]),
            "remaining_account_count": limit_status["remaining_count"],
        }

    @classmethod
    async def get_online_cookies_count(cls) -> int | None:
        """读取真实在线账号数。同一进程并发请求共用查询，失败返回未知。"""
        now = time.monotonic()
        if cls._online_cookies_cache is not None:
            ts, count = cls._online_cookies_cache
            if now - ts < cls._ONLINE_COOKIES_CACHE_TTL:
                return count
        if cls._online_cookies_task is None:
            cls._online_cookies_task = asyncio.create_task(cls._fetch_online_cookies_count())
        # 某个 HTTP 客户端取消等待时，其他请求仍可收到共同的查询结果。
        return await asyncio.shield(cls._online_cookies_task)

    @classmethod
    async def _fetch_online_cookies_count(cls) -> int | None:
        """向消息服务发送一次限时请求，只缓存真实且有效的账号数。"""
        try:
            settings = get_settings()
            url = f"{settings.websocket_service_url.rstrip('/')}/internal/accounts/connection-stats"
            response = await get_http_client().request("GET", url, timeout=3, max_retries=1)
            if isinstance(response, dict) and response.get("success"):
                count = (response.get("data") or {}).get("connected")
                if type(count) is not int or count < 0:
                    raise ValueError("消息服务返回的在线账号数量无效")
                cls._online_cookies_cache = (time.monotonic(), count)
                return count
            raise ValueError(f"消息服务查询失败：{response}")
        except Exception:
            logger.exception("获取仪表盘在线账号数失败")
            return None
        finally:
            cls._online_cookies_task = None

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
        """从数据库读取管理员全局统计和当前用户的账号额度。"""
        today_start = self._build_today_start()
        totals = await self._get_global_totals()
        admin_stats = await DashboardStatsCacheService.get_snapshot(
            "admin_overview", lambda: self._load_admin_overview(today_start), snapshot_day=today_start.date(),
        )
        limit_status = await self._get_limit_status(current_user_id)
        return {
            "total_users": int(admin_stats["total_users"]),
            "total_cookies": totals["total_accounts"],
            "active_cookies": totals["active_accounts"],
            "total_keywords": totals["total_keywords"],
            "total_orders": totals["valid_orders"],
            "today_reply_count": int(admin_stats["today_reply_count"]),
            "yesterday_reply_count": int(admin_stats["yesterday_reply_count"]),
            "total_cards": int(admin_stats["total_cards"]),
            "password_configured": totals["password_configured"],
            "current_user_account_limit": limit_status["account_limit"],
            "current_user_used_account_count": int(limit_status["used_count"]),
            "current_user_remaining_account_count": limit_status["remaining_count"],
        }

    async def get_admin_today_stats(self) -> dict[str, int | float]:
        """获取管理员今日统计。"""
        today_start = self._build_today_start()
        return await DashboardStatsCacheService.get_snapshot(
            "admin_today", lambda: self._load_admin_today(today_start), snapshot_day=today_start.date(),
        )

    async def get_order_amount_trend(self, *, owner_id: int | None, days: int = 30) -> list[dict[str, int | float | str]]:
        """获取近N天订单金额趋势。"""
        today_start = self._build_today_start()
        start_date = today_start - timedelta(days=days - 1)

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
                XYOrder.placed_at < next_day_start(today_start),
                XYOrder.status.notin_(self.CLOSED_ORDER_STATUSES),
            )
            .group_by(func.date(XYOrder.placed_at))
            # 日期顺序由下面的逐日输出保证；MySQL 5.7用ORDER BY NULL免除分组排序。
            .order_by(null())
        )
        if owner_id is not None:
            placed_stmt = placed_stmt.where(XYOrder.owner_id == owner_id)

        placed_rows = {str(row.order_date): row for row in (await self.session.execute(placed_stmt)).all()}

        trend_data: list[dict[str, int | float | str]] = []
        for index in range(days):
            current_day = (start_date + timedelta(days=index)).date()
            row = placed_rows.get(current_day.isoformat())
            trend_data.append(
                {
                    "date": current_day.strftime("%m-%d"),
                    "amount": round(float(row.daily_amount or 0), 2) if row else 0,
                    "count": int(row.daily_count or 0) if row else 0,
                }
            )
        return trend_data
