"""
采集候选账号加载服务

功能：
1. 统一封装"加载生效兜底采集账号"的逻辑（含失效过滤、异常降级、不可用原因明细）
2. 供商品监控采集任务（listing_monitor_task）复用，
   避免兜底加载与失效判定标准在调度任务中重复实现

设计说明：
- 失效判定标准与 load_xy_accounts_by_ids 保持一致；
- 兜底覆盖策略（用户级优先，未配则回退管理员全局兜底）由
  CollectFallbackAccountService.get_effective_fallback_account_ids 决定；
- 数据库异常时返回降级结果（空账号 + 原因明细）而非抛出。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.xy_account import XYAccount
from common.services.collect_fallback_account_service import CollectFallbackAccountService
from common.services.order_account_loader import load_xy_accounts_by_ids


async def load_collect_fallback_accounts(
    owner_id: Optional[int],
    category_id: Optional[int] = None,
    log_prefix: str = "兜底采集账号加载",
) -> Tuple[Dict[str, XYAccount], str]:
    """加载生效的兜底采集账号（含失效过滤、异常降级）。

    覆盖策略（5 层链）：本用户·本分类 → 本用户·无分类 → 管理员·本分类 → 管理员·无分类。

    Returns:
        (account_id -> XYAccount 仅可用账号的字典, 不可用/未配置原因明细)
    """
    try:
        async with async_session_maker() as session:
            svc = CollectFallbackAccountService(session)
            account_ids = await svc.get_effective_fallback_account_ids(owner_id, category_id)
            if not account_ids:
                return {}, "未配置兜底采集账号"
            accounts_map, detail = await load_xy_accounts_by_ids(session, account_ids)
            return accounts_map, detail
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"【{log_prefix}】加载用户{owner_id}兜底采集账号失败，本次按无兜底处理：{exc}")
        return {}, "兜底采集账号加载失败"


async def merge_task_and_fallback_account_ids(
    session: AsyncSession,
    task_account_ids: List[str],
    owner_id: Optional[int],
    category_id: Optional[int] = None,
) -> List[str]:
    """合并监控任务配置的采集账号与生效兜底采集账号（任务在前、兜底在后，去重保序）。

    与下单侧 load_fallback_accounts 的防御性设计保持一致：兜底账号获取失败
    （配置表尚未就绪/数据库异常等）时降级为"仅任务账号"，避免兜底查询异常阻塞
    任务自身采集账号的本轮采集。
    """
    try:
        svc = CollectFallbackAccountService(session)
        fallback_ids = await svc.get_effective_fallback_account_ids(owner_id, category_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"【兜底采集账号合并】获取用户{owner_id}兜底采集账号失败，本次仅用任务账号：{exc}")
        fallback_ids = []
    seen: set[str] = set()
    merged: List[str] = []
    for aid in list(task_account_ids or []) + list(fallback_ids or []):
        key = (aid or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(key)
    return merged


__all__ = [
    "load_collect_fallback_accounts",
    "merge_task_and_fallback_account_ids",
]
