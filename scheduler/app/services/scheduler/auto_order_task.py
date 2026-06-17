"""
采集商品自动下单定时任务

功能：
1. 查询采集商品表中"未下单(is_ordered=0)"的数据（不再要求已私信，只要没下单就下单）
2. 优先使用该商品成功私信的账号(dm_account_id)下单；无私信账号或不可用时，回退到所属监控任务
   配置的下单账号列表(order_account_ids)中的账号轮换下单
3. order.render 渲染 -> order.create 创建订单（拍下）
4. 下单成功后记录订单ID并标记 is_ordered=1

账号规则：
- 账号不可用（Session/Token过期、需登录、风控等）：本次运行不再使用该账号，换下一个账号，不计下单尝试次数
- 业务失败（商品不可买/缺地址等）：累计下单尝试次数(order_attempts)，本次不再换号（下次任务再试）

安全说明：
- 仅做到"创建订单（拍下）"，不自动付款（mtop.order.dopay 会真实扣款）。
- 拍下会生成真实未付款订单，请在业务侧确认风险。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import and_, select

from common.db.session import async_session_maker
from common.models.listing_monitor_item import ListingMonitorItem
from common.models.listing_monitor_task import ListingMonitorTask
from common.models.xy_account import XYAccount
from common.services.xianyu_order_client import XianyuOrderClient

_INACTIVE_STATUSES = {"inactive", "disabled", "suspended", "deleted"}
# 单次任务最多扫描的待下单商品数（全局安全上限；每个监控任务实际处理条数由任务自身的 order_batch_size 控制）
_MAX_ITEMS_SCAN_PER_RUN = 500
# 下单失败最大重试次数（达到后不再重试）
_MAX_ORDER_ATTEMPTS = 3


class AutoOrderTaskService:
    """采集商品自动下单任务服务"""

    def __init__(self, task_name: str = "采集商品自动下单"):
        self.task_name = task_name
        self._lock = asyncio.Lock()

    async def execute(self):
        """执行自动下单任务。"""
        # 并发保护：下单为真实操作，避免定时与手动触发并发导致重复下单
        if self._lock.locked():
            logger.info(f"【{self.task_name}】已有任务正在执行，跳过本次")
            return
        async with self._lock:
            await self._execute_inner()

    async def _execute_inner(self):
        logger.info(f"【{self.task_name}】开始执行")
        start_time = datetime.now()

        try:
            items = await self._get_items_to_order()
            if not items:
                logger.info(f"【{self.task_name}】没有待下单的采集商品，结束")
                return

            logger.info(f"【{self.task_name}】查询到 {len(items)} 条待下单商品")

            # 监控任务ID -> 下单账号字典 {account_id: XYAccount}（缓存，仅含可用账号）
            task_accounts_cache: Dict[int, Dict[str, XYAccount]] = {}
            # 监控任务ID -> 下单账号配置顺序（缓存，用于回退轮换）
            task_order_cache: Dict[int, List[str]] = {}
            # 监控任务ID -> 每次最多下单条数（缓存）
            task_batch_cache: Dict[int, int] = {}
            # 监控任务ID -> 回退轮换指针
            task_rr: Dict[int, int] = {}
            # 监控任务ID -> 本次已实际下单处理条数（达到 order_batch_size 后该任务本次不再处理）
            task_done: Dict[int, int] = {}
            # 本次运行被判定不可用的账号（停用至本次结束）
            disabled_accounts: set[str] = set()

            ordered = 0
            skipped_no_account = 0
            skipped_batch_full = 0
            failed = 0

            for pk, item_id, task_id, dm_account_id in items:
                if task_id not in task_accounts_cache:
                    accounts_map, order_list, batch_size = await self._load_task_accounts(task_id)
                    task_accounts_cache[task_id] = accounts_map
                    task_order_cache[task_id] = order_list
                    task_batch_cache[task_id] = batch_size
                accounts_map = task_accounts_cache[task_id]
                order_list = task_order_cache[task_id]
                batch_size = task_batch_cache.get(task_id, 5)

                # 该任务本次已达每次最多下单条数：跳过
                if task_done.get(task_id, 0) >= batch_size:
                    skipped_batch_full += 1
                    continue

                # 构造候选账号顺序：优先成功私信账号，再回退到下单账号列表其他账号
                candidates = self._build_candidates(
                    dm_account_id, order_list, accounts_map, task_rr.get(task_id, 0)
                )
                task_rr[task_id] = task_rr.get(task_id, 0) + 1

                usable = [a for a in candidates if a.account_id not in disabled_accounts]
                if not usable:
                    skipped_no_account += 1
                    continue

                result = await self._order_for_item(pk, item_id, usable, disabled_accounts)
                if result == "ordered":
                    ordered += 1
                    task_done[task_id] = task_done.get(task_id, 0) + 1
                elif result == "no_account":
                    skipped_no_account += 1
                else:
                    # failed：已实际尝试下单（render/create），计入该任务本次处理条数
                    failed += 1
                    task_done[task_id] = task_done.get(task_id, 0) + 1

                await asyncio.sleep(1)

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"【{self.task_name}】执行完成：待下单{len(items)}，成功{ordered}，"
                f"达批量上限跳过{skipped_batch_full}，无可用账号跳过{skipped_no_account}，失败{failed}，"
                f"停用账号{len(disabled_accounts)}，耗时{elapsed:.2f}秒"
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"【{self.task_name}】执行异常: {exc}")

    async def _get_items_to_order(self) -> List[Tuple[int, str, int, Optional[str]]]:
        """查询未下单的采集商品（不再要求已私信）。

        Returns: (主键id, item_id, monitor_task_id, dm_account_id) 列表
        """
        async with async_session_maker() as session:
            stmt = (
                select(
                    ListingMonitorItem.id,
                    ListingMonitorItem.item_id,
                    ListingMonitorItem.monitor_task_id,
                    ListingMonitorItem.dm_account_id,
                )
                .where(
                    and_(
                        ListingMonitorItem.is_ordered.is_(False),
                        ListingMonitorItem.order_attempts < _MAX_ORDER_ATTEMPTS,
                    )
                )
                .order_by(ListingMonitorItem.id.asc())
                .limit(_MAX_ITEMS_SCAN_PER_RUN)
            )
            rows = (await session.execute(stmt)).all()
            return [(r[0], r[1], r[2], r[3]) for r in rows]

    async def _load_task_accounts(self, task_id: int) -> Tuple[Dict[str, XYAccount], List[str], int]:
        """加载监控任务配置的下单账号（任务须未删除且启用；过滤禁用/空Cookie）。

        Returns: ({account_id: XYAccount 仅可用账号}, 配置顺序的account_id列表, order_batch_size)
        """
        async with async_session_maker() as session:
            task = (
                await session.execute(
                    select(
                        ListingMonitorTask.order_account_ids,
                        ListingMonitorTask.order_batch_size,
                    ).where(
                        ListingMonitorTask.id == task_id,
                        ListingMonitorTask.is_deleted.is_(False),
                        ListingMonitorTask.is_enabled.is_(True),
                    )
                )
            ).first()
            if not task or not task[0]:
                return {}, [], 5
            account_ids = list(task[0] or [])
            batch_size = task[1] if task[1] and task[1] > 0 else 5
            if not account_ids:
                return {}, [], batch_size
            rows = list(
                (
                    await session.execute(
                        select(XYAccount).where(XYAccount.account_id.in_(account_ids))
                    )
                ).scalars().all()
            )

        accounts_map: Dict[str, XYAccount] = {}
        for row in rows:
            if not row.cookie:
                continue
            if (row.status or "active").strip().lower() in _INACTIVE_STATUSES:
                continue
            accounts_map[row.account_id] = row
        return accounts_map, account_ids, batch_size

    def _build_candidates(
        self,
        dm_account_id: Optional[str],
        order_list: List[str],
        accounts_map: Dict[str, XYAccount],
        rr_start: int,
    ) -> List[XYAccount]:
        """构造候选下单账号顺序：优先成功私信账号，再回退到下单账号列表其他账号（轮换）。"""
        candidates: List[XYAccount] = []
        seen: set[str] = set()

        # 1) 优先使用成功私信的账号
        if dm_account_id and dm_account_id in accounts_map:
            candidates.append(accounts_map[dm_account_id])
            seen.add(dm_account_id)

        # 2) 回退到下单账号列表中的其他账号（按轮换顺序）
        n = len(order_list)
        for offset in range(n):
            aid = order_list[(rr_start + offset) % n]
            if aid in seen:
                continue
            acc = accounts_map.get(aid)
            if acc:
                candidates.append(acc)
                seen.add(aid)
        return candidates

    async def _order_for_item(
        self,
        pk: int,
        item_id: str,
        accounts: List[XYAccount],
        disabled_accounts: set[str],
    ) -> str:
        """对单个商品按候选账号顺序下单。

        Returns: "ordered" / "failed" / "no_account"
        """
        tried = 0
        for acc in accounts:
            if acc.account_id in disabled_accounts:
                continue
            tried += 1
            status, biz_order_id, fail_reason = await self._order_one(acc, item_id)
            if status == "account_invalid":
                disabled_accounts.add(acc.account_id)
                logger.warning(
                    f"【{self.task_name}】账号 {acc.account_id} 下单不可用（{fail_reason}），"
                    f"本次停用，尝试下一个账号"
                )
                continue
            if status == "success":
                await self._record_result(pk, True, biz_order_id, None)
                return "ordered"
            # 业务失败：累计尝试次数，本次不再换号
            await self._record_result(pk, False, None, fail_reason)
            return "failed"

        # 所有候选账号都不可用
        return "no_account" if tried == 0 else "failed"

    async def _order_one(self, account: XYAccount, item_id: str) -> Tuple[str, Optional[str], Optional[str]]:
        """对单个商品执行下单（render -> create）。

        Returns: (status, 订单ID, 失败原因)，status ∈ {"success","account_invalid","failed"}
        """
        client = XianyuOrderClient(account.account_id, account.cookie, owner_id=account.owner_id)
        result = await client.place_order(item_id)
        # 令牌可能已刷新：回写内存账号Cookie，供同账号后续商品复用
        account.cookie = client.cookies_str

        status = result.get("status")
        reason = result.get("error")
        if status == "account_invalid":
            return "account_invalid", None, reason
        if status != "success":
            logger.warning(
                f"【{self.task_name}】商品 {item_id} 下单失败（账号 {account.account_id}）：{reason}"
            )
            return "failed", None, reason

        biz_order_id = result.get("order_id")
        logger.info(
            f"【{self.task_name}】商品 {item_id} 下单成功（拍下）："
            f"账号={account.account_id}，订单ID={biz_order_id}"
        )
        return "success", biz_order_id, None

    async def _record_result(
        self, pk: int, ok: bool, biz_order_id: Optional[str], fail_reason: Optional[str]
    ) -> None:
        """记录下单结果并累计尝试次数。

        - 成功：is_ordered=true（终态），记录 order_id；
        - 失败：is_ordered 保持 false，仅累计 order_attempts，达上限后由查询条件自动排除（停止重试）。

        注意：成功后回写失败会导致订单已拍下但未标记，下次可能重复下单，故失败时 CRITICAL 告警。
        """
        try:
            async with async_session_maker() as session:
                item = (
                    await session.execute(
                        select(ListingMonitorItem).where(ListingMonitorItem.id == pk)
                    )
                ).scalar_one_or_none()
                if not item:
                    return
                item.order_attempts = (item.order_attempts or 0) + 1
                if ok:
                    item.is_ordered = True
                    item.order_status = "success"
                    item.order_fail_reason = None
                    if biz_order_id:
                        item.order_id = biz_order_id[:64]
                else:
                    item.order_status = "failed"
                    item.order_fail_reason = str(fail_reason)[:500] if fail_reason else None
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            if ok:
                logger.critical(
                    f"【{self.task_name}】订单已拍下但标记失败！采集商品id={pk}，订单ID={biz_order_id}，"
                    f"请人工核对避免重复下单：{exc}"
                )
            else:
                logger.error(f"【{self.task_name}】下单结果回写失败 采集商品id={pk}：{exc}")


# 全局实例
auto_order_task_service = AutoOrderTaskService(task_name="采集商品自动下单")
