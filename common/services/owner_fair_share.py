"""
按归属分组的公平配额分配

功能：
1. 水位填充分配配额（`allocate_owner_quotas`）：把有限额度公平分给多个分组
2. 分组顺序旋转（`order_owner_ids`）：额度少于分组数时轮流优先，避免固定顺序饿死尾部
3. 轮转交错合并（`interleave_by_owner`）：把各分组取到的数据按轮次交错成一个处理队列

适用场景：
定时任务从全局表里"每轮取 N 条"处理时，若直接 `ORDER BY id LIMIT N`，
数据量大的用户/任务会长期占满额度，其他用户的数据永远轮不到。
这里的分组键可以是归属用户ID，也可以是监控任务ID（两级配额），键只需可排序/可哈希。

使用方：采集商品自动下单取数（auto_order_queue）、采集商品卖家ID补全取数（seller_fill_queue）。
"""
from __future__ import annotations

from typing import Dict, Hashable, List, Optional, Sequence, TypeVar

# 分组键：归属用户ID（可为 None 表示无归属）或监控任务ID
GroupKey = TypeVar("GroupKey", bound=Hashable)


def order_owner_ids(
    pending_counts: Dict[Optional[int], int], rotation: int = 0
) -> List[Optional[int]]:
    """返回本轮的分组处理顺序（按键升序、None 排最后，并按轮次旋转起点）。

    旋转起点的意义：当"有待处理数据的分组数"多于本轮总额度时，每个分组只能分到 1 条，
    额度用完后排在后面的分组本轮一条都分不到；若顺序恒定，这些分组会被永久饿死。
    每轮把起点往后挪一位，保证所有分组轮流被优先处理。

    Args:
        pending_counts: 分组键 -> 待处理条数
        rotation: 本轮轮次（任意单调递增整数即可）

    Returns:
        排好序（并旋转过起点）的分组键列表
    """
    keys = sorted(pending_counts.keys(), key=lambda key: (key is None, key or 0))
    if not keys:
        return keys
    shift = rotation % len(keys)
    return keys[shift:] + keys[:shift]


def allocate_owner_quotas(pending_counts: Dict[GroupKey, int], total: int) -> Dict[GroupKey, int]:
    """按水位填充为各分组分配本轮配额。

    逐轮把"剩余额度"在仍有待处理数据的分组间均分（每轮至少分 1 条），
    分组取满自身待处理数后退出分配，剩余额度继续分给数据更多的分组，
    从而既公平（个个有份）又不浪费（额度尽量用满）。

    传入字典的顺序即分配优先级（额度不够时靠前的分组先拿），
    调用方可先用 order_owner_ids 按轮次旋转顺序。

    Args:
        pending_counts: 分组键 -> 待处理条数
        total: 本轮总额度

    Returns:
        分组键 -> 本轮该分组的取数上限（未分到额度的分组不出现在结果中）
    """
    quotas: Dict[GroupKey, int] = {}
    active = [key for key, count in pending_counts.items() if count > 0]
    if not active or total <= 0:
        return quotas

    remaining = total
    while remaining > 0 and active:
        share = max(1, remaining // len(active))
        for key in list(active):
            if remaining <= 0:
                break
            take = min(share, pending_counts[key] - quotas.get(key, 0), remaining)
            if take <= 0:
                active.remove(key)
                continue
            quotas[key] = quotas.get(key, 0) + take
            remaining -= take
            if quotas[key] >= pending_counts[key]:
                active.remove(key)
    return quotas


def interleave_by_owner(buckets: Sequence[Sequence], max_items: int) -> List:
    """按分组轮转交错合并（每轮各取一条），总数不超过 max_items。

    交错的意义：本轮若因服务重启/执行超时被中断，每个分组都已被处理了一部分，
    不会出现"排在前面的分组吃完时间、后面的分组一条都没轮到"。

    Args:
        buckets: 各分组已取到的数据（分组内部顺序由调用方决定，通常按主键升序）
        max_items: 合并结果的条数上限

    Returns:
        交错合并后的列表
    """
    merged: List = []
    if not buckets or max_items <= 0:
        return merged
    depth = max(len(bucket) for bucket in buckets)
    for index in range(depth):
        for bucket in buckets:
            if index >= len(bucket):
                continue
            merged.append(bucket[index])
            if len(merged) >= max_items:
                return merged
    return merged


__all__ = [
    "allocate_owner_quotas",
    "interleave_by_owner",
    "order_owner_ids",
]
