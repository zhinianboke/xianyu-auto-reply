"""
下单候选账号加载服务

功能：
1. 统一封装"按账号ID列表加载 XYAccount 并过滤失效（未登录/已停用/不存在）"的逻辑
2. 统一封装"加载生效兜底下单账号"的逻辑（含失效过滤、异常降级、不可用原因明细）
3. 供采集后直接下单（listing_monitor_task）与定时下单（auto_order_task）两处复用，
   避免兜底加载与失效判定标准在多个调度任务中重复实现导致行为漂移

设计说明：
- 失效判定标准（INACTIVE_STATUSES）与 Cookie 空判定在此处集中维护；
- 兜底覆盖策略（用户级优先，未配则回退管理员全局兜底）由
  OrderFallbackAccountService.get_effective_fallback_account_ids 决定，本模块不重复实现；
- 数据库异常时返回降级结果（空账号 + 原因明细）而非抛出，避免阻塞整轮下单调度。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.xy_account import XYAccount
from common.services.order_fallback_account_service import OrderFallbackAccountService

INACTIVE_STATUSES: set[str] = {"inactive", "disabled", "suspended", "deleted"}


async def load_xy_accounts_by_ids(
    session: AsyncSession, account_ids: List[str]
) -> Tuple[Dict[str, XYAccount], str]:
    """按账号ID列表加载 XYAccount，过滤未登录(Cookie 空)/已停用/不存在的账号。

    Args:
        session: 已开启的数据库会话
        account_ids: 待加载的账号ID列表（顺序由调用方维护）

    Returns:
        (account_id -> XYAccount 仅可用账号的字典, 不可用原因明细字符串)
        明细按"账号X 未登录(Cookie为空)"、"账号Y 已停用(状态=...)"、"账号Z 不存在(已被删除)"拼接
    """
    if not account_ids:
        return {}, ""

    rows = list(
        (
            await session.execute(
                select(XYAccount).where(XYAccount.account_id.in_(account_ids))
            )
        ).scalars().all()
    )

    accounts_map: Dict[str, XYAccount] = {}
    found_ids: set[str] = set()
    skip_reasons: List[str] = []
    for row in rows:
        found_ids.add(row.account_id)
        if not row.cookie:
            skip_reasons.append(f"账号{row.account_id} 未登录(Cookie为空)")
            continue
        status = (row.status or "active").strip().lower()
        if status in INACTIVE_STATUSES:
            skip_reasons.append(f"账号{row.account_id} 已停用(状态={status})")
            continue
        accounts_map[row.account_id] = row
    for aid in account_ids:
        if aid not in found_ids:
            skip_reasons.append(f"账号{aid} 不存在(已被删除)")

    return accounts_map, "；".join(skip_reasons)


async def load_fallback_accounts(
    owner_id: Optional[int],
    category_id: Optional[int] = None,
    log_prefix: str = "兜底账号加载",
) -> Tuple[Dict[str, XYAccount], str]:
    """加载生效的兜底下单账号（含失效过滤、异常降级）。

    覆盖策略（5 层链，由 OrderFallbackAccountService.get_effective_fallback_account_ids 决定）：
    本用户·本分类 → 本用户·无分类 → 管理员·本分类 → 管理员·无分类。

    Args:
        owner_id: 商品所属用户ID（可为 None 表示无归属用户）
        category_id: 任务所属分类ID（NULL=无分类；用于按分类取本分类兜底）
        log_prefix: 日志前缀，便于在调度任务日志中识别来源

    Returns:
        (account_id -> XYAccount 仅可用账号的字典, 不可用/未配置原因明细)
        - 未配置兜底：({}, "未配置兜底下单账号")
        - 数据库异常：({}, "兜底下单账号加载失败")
        - 部分/全部失效：(可用账号字典, 各失效账号的详细原因)
    """
    try:
        async with async_session_maker() as session:
            svc = OrderFallbackAccountService(session)
            account_ids = await svc.get_effective_fallback_account_ids(owner_id, category_id)
            if not account_ids:
                return {}, "未配置兜底下单账号"
            accounts_map, detail = await load_xy_accounts_by_ids(session, account_ids)
            return accounts_map, detail
    except Exception as exc:  # noqa: BLE001
        # 配置表尚未就绪或数据库异常时降级为"无兜底"，避免中断整轮下单调度
        logger.warning(f"【{log_prefix}】加载用户{owner_id}兜底下单账号失败，本次按无兜底处理：{exc}")
        return {}, "兜底下单账号加载失败"


__all__ = [
    "INACTIVE_STATUSES",
    "load_xy_accounts_by_ids",
    "load_fallback_accounts",
]
