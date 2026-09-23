"""
采集商品卖家ID补全队列取数

功能：
1. 按"卖家真实ID为空 + 未标记补全失败 + 下单状态可补全 + 最近N天采集入库"筛选待补全商品
2. 两级公平配额取数：先按归属用户分额度，再在用户内部按监控任务分额度，
   最后按用户/任务轮转交错返回

设计说明：
- 原实现是全局 `ORDER BY id ASC LIMIT 300`：采集量大的用户（或同一用户里数据量大的任务）
  会吃满每轮全部名额，其他用户当天的商品补不上卖家ID，进而私信/下单全部卡住。
- 配额分配/顺序旋转/交错合并复用公共模块 owner_fair_share，与自动下单取数
  （auto_order_queue）共用同一套公平策略，避免两处各写一版导致行为漂移。
- 时间窗口沿用原有口径：只补全当天与昨天入库的商品（约24小时容错窗口），
  更早的遗留数据不再占用补全配额。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select

from common.db.session import async_session_maker
from common.models.listing_monitor_item import ListingMonitorItem
from common.services.owner_fair_share import (
    allocate_owner_quotas,
    interleave_by_owner,
    order_owner_ids,
)
from common.utils.time_utils import get_beijing_now_naive

# 单次任务最多处理的待补全商品数，避免单次运行过久
MAX_ITEMS_PER_RUN = 300
# 待补全商品回溯天数：以北京时间今天 00:00 前推该天数为入库时间下限，1=覆盖今天与昨天
SELLER_FILL_LOOKBACK_DAYS = 1

# 待补全商品行：(主键id, item_id, monitor_task_id, owner_id)
SellerFillQueueRow = Tuple[int, str, int, Optional[int]]


def seller_fill_cutoff_time() -> datetime:
    """返回待补全商品的入库时间下限（北京时间 naive）。

    Returns:
        北京时间今天 00:00 前推 SELLER_FILL_LOOKBACK_DAYS 天的时间点
    """
    today_start = get_beijing_now_naive().replace(hour=0, minute=0, second=0, microsecond=0)
    return today_start - timedelta(days=SELLER_FILL_LOOKBACK_DAYS)


def _pending_conditions(cutoff: datetime) -> list:
    """构造"待补全卖家ID"的筛选条件。

    条件与原实现保持一致：
    - 仅处理回溯窗口内采集入库的商品；
    - 卖家真实ID为空；
    - 排除已明确补全失败、不再补全的商品（如跨境商品/已下架）；
    - 下单状态仅取 未下单(NULL)/已下单/下单失败/无可用账号，排除重复(duplicate)
      （重复商品已被同用户其他任务下单，无需补全卖家详情）。

    Args:
        cutoff: 采集入库时间下限（由调用方一次算好并复用，避免同一轮取数跨零点时窗口不一致）
    """
    return [
        ListingMonitorItem.created_at >= cutoff,
        or_(
            ListingMonitorItem.seller_user_id.is_(None),
            ListingMonitorItem.seller_user_id == "",
        ),
        or_(
            ListingMonitorItem.seller_fill_status.is_(None),
            ListingMonitorItem.seller_fill_status != "failed",
        ),
        or_(
            ListingMonitorItem.order_status.is_(None),
            ListingMonitorItem.order_status.in_(["success", "failed", "no_account"]),
        ),
    ]


def _group_condition(column, value):
    """构造分组等值条件（值为 None 时用 IS NULL，避免 `= NULL` 恒不成立）。"""
    return column.is_(None) if value is None else column == value


async def _fetch_group_rows(
    session, cutoff: datetime, owner_id: Optional[int], task_id: Optional[int], limit: int
) -> List[SellerFillQueueRow]:
    """按 (归属用户, 监控任务) 取该分组本轮配额内的待补全商品（按主键升序）。"""
    stmt = (
        select(
            ListingMonitorItem.id,
            ListingMonitorItem.item_id,
            ListingMonitorItem.monitor_task_id,
            ListingMonitorItem.owner_id,
        )
        .where(
            and_(
                *_pending_conditions(cutoff),
                _group_condition(ListingMonitorItem.owner_id, owner_id),
                _group_condition(ListingMonitorItem.monitor_task_id, task_id),
            )
        )
        .order_by(ListingMonitorItem.id.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


async def fetch_items_to_fill(
    max_items: int = MAX_ITEMS_PER_RUN, owner_rotation: int = 0
) -> List[SellerFillQueueRow]:
    """查询本轮待补全卖家ID的采集商品（两级配额取数、轮转交错返回）。

    Args:
        max_items: 本轮最多取多少条（默认 MAX_ITEMS_PER_RUN）
        owner_rotation: 本轮轮次，用于旋转用户与任务的处理起点（见 order_owner_ids）

    Returns:
        (主键id, item_id, monitor_task_id, owner_id) 列表
    """
    # 窗口下限一次算好，本轮所有查询复用，避免跨零点时前后查询窗口不一致
    cutoff = seller_fill_cutoff_time()
    async with async_session_maker() as session:
        group_rows = (
            await session.execute(
                select(
                    ListingMonitorItem.owner_id,
                    ListingMonitorItem.monitor_task_id,
                    func.count(),
                )
                .where(and_(*_pending_conditions(cutoff)))
                .group_by(ListingMonitorItem.owner_id, ListingMonitorItem.monitor_task_id)
            )
        ).all()
        if not group_rows:
            return []

        # 汇总为「用户 -> 总数」与「用户 -> {任务 -> 条数}」
        owner_totals: Dict[Optional[int], int] = {}
        owner_task_counts: Dict[Optional[int], Dict[Optional[int], int]] = {}
        for owner_id, task_id, count in group_rows:
            count = int(count or 0)
            owner_totals[owner_id] = owner_totals.get(owner_id, 0) + count
            owner_task_counts.setdefault(owner_id, {})[task_id] = count

        # 一级配额：按用户分配本轮总额度
        ordered_owners = order_owner_ids(owner_totals, owner_rotation)
        owner_quotas = allocate_owner_quotas(
            {owner_id: owner_totals[owner_id] for owner_id in ordered_owners}, max_items
        )

        owner_buckets: List[List[SellerFillQueueRow]] = []
        for owner_id in ordered_owners:
            owner_quota = owner_quotas.get(owner_id, 0)
            if owner_quota <= 0:
                continue
            # 二级配额：在该用户额度内按监控任务再分配，避免单个任务的存量数据吃满用户额度
            task_counts = owner_task_counts.get(owner_id, {})
            ordered_tasks = order_owner_ids(task_counts, owner_rotation)
            task_quotas = allocate_owner_quotas(
                {task_id: task_counts[task_id] for task_id in ordered_tasks}, owner_quota
            )
            task_buckets: List[List[SellerFillQueueRow]] = []
            for task_id in ordered_tasks:
                task_quota = task_quotas.get(task_id, 0)
                if task_quota <= 0:
                    continue
                rows = await _fetch_group_rows(session, cutoff, owner_id, task_id, task_quota)
                if rows:
                    task_buckets.append(rows)
            merged_owner_rows = interleave_by_owner(task_buckets, owner_quota)
            if merged_owner_rows:
                owner_buckets.append(merged_owner_rows)

    return interleave_by_owner(owner_buckets, max_items)


__all__ = [
    "MAX_ITEMS_PER_RUN",
    "SELLER_FILL_LOOKBACK_DAYS",
    "SellerFillQueueRow",
    "fetch_items_to_fill",
    "seller_fill_cutoff_time",
]
