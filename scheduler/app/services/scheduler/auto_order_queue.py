"""
采集商品待下单队列取数

功能：
1. 按"未下单 + 未达下单尝试上限 + 最近N天采集入库"筛选待下单的采集商品
2. 按归属用户分配本轮取数配额，并按用户轮转交错返回，避免单个用户的存量数据
   占满本轮全部额度、把其他用户的新商品挤出队列

设计说明：
- 时间窗口：无可用下单账号的商品不累加 order_attempts（账号不可用属环境问题，
  需等账号恢复后继续重试）。若不加时间窗口，这类商品会永久留在待下单队列，
  并因"按 id 升序取数"长期占据队列头部——先挤掉其他用户的新商品，
  积累到扫描上限后所有用户都不再下单。窗口口径与卖家ID补全/发送私信任务保持一致。
- 用户配额：配额分配/顺序旋转/交错合并三件事由公共模块 owner_fair_share 实现，
  与卖家ID补全取数（seller_fill_queue）共用同一套公平策略。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select

from common.db.session import async_session_maker
from common.models.listing_monitor_item import ListingMonitorItem
from common.services.owner_fair_share import (
    allocate_owner_quotas,
    interleave_by_owner,
    order_owner_ids,
)
from common.utils.time_utils import get_beijing_now_naive

# 单次任务最多扫描的待下单商品数（全局安全上限；每个监控任务实际处理条数由任务自身的 order_batch_size 控制）
MAX_ITEMS_SCAN_PER_RUN = 500
# 下单失败最大重试次数（达到后不再重试）
MAX_ORDER_ATTEMPTS = 3
# 待下单商品回溯天数：以北京时间今天 00:00 前推该天数为入库时间下限，1=覆盖今天与昨天
ORDER_ITEM_LOOKBACK_DAYS = 1

# 待下单商品行：(主键id, item_id, monitor_task_id, dm_account_id, owner_id)
OrderQueueRow = Tuple[int, str, int, Optional[str], Optional[int]]


def order_item_cutoff_time() -> datetime:
    """返回待下单商品的入库时间下限（北京时间 naive）。

    Returns:
        北京时间今天 00:00 前推 ORDER_ITEM_LOOKBACK_DAYS 天的时间点
    """
    today_start = get_beijing_now_naive().replace(hour=0, minute=0, second=0, microsecond=0)
    return today_start - timedelta(days=ORDER_ITEM_LOOKBACK_DAYS)


def _pending_conditions(cutoff: datetime) -> list:
    """构造"待下单"筛选条件：未下单 + 未达尝试上限 + 在回溯窗口内采集入库。

    Args:
        cutoff: 采集入库时间下限（由调用方一次算好并复用，避免同一轮取数跨过零点时
            前后两次查询用了不同的窗口，导致统计数与实际取数不一致）
    """
    return [
        ListingMonitorItem.is_ordered.is_(False),
        ListingMonitorItem.order_attempts < MAX_ORDER_ATTEMPTS,
        ListingMonitorItem.created_at >= cutoff,
    ]


async def fetch_items_to_order(
    max_items: int = MAX_ITEMS_SCAN_PER_RUN, owner_rotation: int = 0
) -> List[OrderQueueRow]:
    """查询本轮待下单的采集商品（按用户配额取数、按用户轮转交错返回）。

    Args:
        max_items: 本轮最多取多少条（默认 MAX_ITEMS_SCAN_PER_RUN）
        owner_rotation: 本轮轮次，用于旋转用户处理起点（见 order_owner_ids）

    Returns:
        (主键id, item_id, monitor_task_id, dm_account_id, owner_id) 列表
    """
    # 窗口下限一次算好，本轮所有查询复用，避免跨零点时前后查询窗口不一致
    cutoff = order_item_cutoff_time()
    async with async_session_maker() as session:
        owner_rows = (
            await session.execute(
                select(ListingMonitorItem.owner_id, func.count())
                .where(and_(*_pending_conditions(cutoff)))
                .group_by(ListingMonitorItem.owner_id)
            )
        ).all()
        raw_counts = {row[0]: int(row[1] or 0) for row in owner_rows}
        # 按处理顺序重建字典：水位填充的"最后几条零头"也按该顺序分配，保证轮次间公平
        pending_counts = {
            owner_id: raw_counts[owner_id]
            for owner_id in order_owner_ids(raw_counts, owner_rotation)
        }
        quotas = allocate_owner_quotas(pending_counts, max_items)
        if not quotas:
            return []

        buckets: List[List[OrderQueueRow]] = []
        for owner_id in pending_counts:
            if owner_id not in quotas:
                continue
            owner_condition = (
                ListingMonitorItem.owner_id.is_(None)
                if owner_id is None
                else ListingMonitorItem.owner_id == owner_id
            )
            stmt = (
                select(
                    ListingMonitorItem.id,
                    ListingMonitorItem.item_id,
                    ListingMonitorItem.monitor_task_id,
                    ListingMonitorItem.dm_account_id,
                    ListingMonitorItem.owner_id,
                )
                .where(and_(*_pending_conditions(cutoff), owner_condition))
                .order_by(ListingMonitorItem.id.asc())
                .limit(quotas[owner_id])
            )
            rows = (await session.execute(stmt)).all()
            if rows:
                buckets.append([(r[0], r[1], r[2], r[3], r[4]) for r in rows])

    return interleave_by_owner(buckets, max_items)


__all__ = [
    "MAX_ITEMS_SCAN_PER_RUN",
    "MAX_ORDER_ATTEMPTS",
    "ORDER_ITEM_LOOKBACK_DAYS",
    "OrderQueueRow",
    "allocate_owner_quotas",
    "fetch_items_to_order",
    "interleave_by_owner",
    "order_item_cutoff_time",
    "order_owner_ids",
]
