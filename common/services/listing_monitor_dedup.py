"""
商品监控下单去重判断

功能：
判断同一用户（owner_id）名下某商品（item_id）是否已存在"已下单成功"的采集记录。
用于防止多个监控任务采集到同一商品时重复下单（采集商品表唯一键为
(monitor_task_id, item_id)，同一用户的不同任务会各自存一条同 item_id 记录）。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.listing_monitor_item import ListingMonitorItem


async def has_owner_ordered_item(
    session: AsyncSession,
    owner_id: Optional[int],
    item_id: str,
) -> bool:
    """判断同一用户下该商品是否已有下单成功（is_ordered=true）的记录。

    Args:
        session: 数据库会话
        owner_id: 归属用户ID（None 时不按用户过滤，仅按商品ID）
        item_id: 闲鱼商品ID

    Returns:
        True 表示该用户名下该商品已下单成功，应跳过重复下单
    """
    stmt = select(ListingMonitorItem.id).where(
        ListingMonitorItem.item_id == str(item_id),
        ListingMonitorItem.is_ordered.is_(True),
    )
    if owner_id is not None:
        stmt = stmt.where(ListingMonitorItem.owner_id == owner_id)
    return (await session.execute(stmt.limit(1))).scalar_one_or_none() is not None


__all__ = ["has_owner_ordered_item"]
