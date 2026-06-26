"""
采集商品自动下单定时任务

功能：
1. 查询采集商品表中"未下单(is_ordered=0)"的数据（不再要求已私信，只要没下单就下单）
2. 优先使用该商品成功私信的账号(dm_account_id)下单；无私信账号或不可用时，回退到所属监控任务
   配置的下单账号列表(order_account_ids)中的账号轮换下单
3. order.render 渲染 -> order.create 创建订单（拍下）
4. 下单成功后记录订单ID并标记 is_ordered=1

账号规则：
- 账号不可用（Session/Token过期、需登录、风控等）：本次运行不再使用该账号（全局停用至本轮结束），换下一个账号，不计下单尝试次数
- 业务失败（商品不可买/缺地址/权限受限等）：换下一个候选账号继续尝试（不全局停用，可能仅该商品不可买）；
  所有候选账号都尝试过仍未成功，才累计下单尝试次数(order_attempts)并记录失败原因

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
from common.services.listing_monitor_dedup import has_owner_ordered_item
from common.services.order_account_loader import (
    load_fallback_accounts,
    load_xy_accounts_by_ids,
)
from common.services.xianyu_order_client import XianyuOrderClient
from common.utils.time_utils import get_beijing_now_naive

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
            # 监控任务ID -> 任务名称(监控关键字)（缓存）
            task_name_cache: Dict[int, str] = {}
            # 监控任务ID -> 不可用账号精确明细（缓存）
            task_detail_cache: Dict[int, str] = {}
            # 监控任务ID -> 所属分类ID（缓存，用于按分类取兜底）
            task_category_cache: Dict[int, Optional[int]] = {}
            # (用户ID,分类ID) -> 兜底下单账号字典 {account_id: XYAccount}（缓存，仅含可用账号）
            fallback_accounts_cache: Dict[tuple, Dict[str, XYAccount]] = {}
            # (用户ID,分类ID) -> 兜底账号不可用明细（缓存）
            fallback_detail_cache: Dict[tuple, str] = {}
            # (用户ID,分类ID) -> 兜底账号轮换指针
            fallback_rr: Dict[tuple, int] = {}
            # 监控任务ID -> 回退轮换指针
            task_rr: Dict[int, int] = {}
            # 监控任务ID -> 本次已实际下单处理条数（达到 order_batch_size 后该任务本次不再处理）
            task_done: Dict[int, int] = {}
            # 本次运行被判定不可用的账号（停用至本次结束）
            disabled_accounts: set[str] = set()
            # 已针对"无可用账号"打印过明细的监控任务，避免逐条商品刷屏
            warned_no_account_tasks: set[int] = set()

            ordered = 0
            skipped_no_account = 0
            skipped_batch_full = 0
            skipped_duplicate = 0
            failed = 0
            # 本轮已下单成功的商品ID集合，避免同一批次内多任务同商品重复下单
            ordered_item_ids: set[str] = set()

            for pk, item_id, task_id, dm_account_id, owner_id in items:
                # 去重：同一用户该商品已下单成功（历史已下单 或 本轮已下单），跳过重复下单
                if item_id in ordered_item_ids or await self._owner_already_ordered(owner_id, item_id):
                    await self._mark_duplicate(pk)
                    skipped_duplicate += 1
                    continue

                if task_id not in task_accounts_cache:
                    accounts_map, order_list, batch_size, task_name, detail, category_id = await self._load_task_accounts(task_id)
                    task_accounts_cache[task_id] = accounts_map
                    task_order_cache[task_id] = order_list
                    task_batch_cache[task_id] = batch_size
                    task_name_cache[task_id] = task_name
                    task_detail_cache[task_id] = detail
                    task_category_cache[task_id] = category_id
                accounts_map = task_accounts_cache[task_id]
                order_list = task_order_cache[task_id]
                batch_size = task_batch_cache.get(task_id, 5)
                category_id = task_category_cache.get(task_id)
                fb_key = (owner_id, category_id)

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

                # 追加用户级兜底下单账号作为后备：任务自身账号优先，兜底其次
                # （任务账号在加载时可用但下单时失效的场景，也能继续用兜底账号兜住）
                if fb_key not in fallback_accounts_cache:
                    fb_map, fb_detail = await self._load_fallback_accounts(owner_id, category_id)
                    fallback_accounts_cache[fb_key] = fb_map
                    fallback_detail_cache[fb_key] = fb_detail
                fb_accounts = fallback_accounts_cache[fb_key]
                fb_usable = [a for a in fb_accounts.values() if a.account_id not in disabled_accounts]
                if fb_usable:
                    # 轮换兜底账号起点，避免总是从同一个账号开始
                    start = fallback_rr.get(fb_key, 0)
                    fallback_rr[fb_key] = start + 1
                    n = len(fb_usable)
                    fb_usable = [fb_usable[(start + i) % n] for i in range(n)]

                # 合并候选：任务账号在前、兜底在后，按 account_id 去重
                seen_ids: set[str] = set()
                order_candidates: List[XYAccount] = []
                for acc in usable + fb_usable:
                    if acc.account_id in seen_ids:
                        continue
                    seen_ids.add(acc.account_id)
                    order_candidates.append(acc)

                if not order_candidates:
                    skipped_no_account += 1
                    task_name = task_name_cache.get(task_id, f"id={task_id}")
                    task_reason = task_detail_cache.get(task_id) or "配置账号本次运行均失效（Token过期/需登录/风控）"
                    fb_detail = fallback_detail_cache.get(fb_key, "未配置兜底下单账号")
                    reason = f"任务下单账号不可用（{task_reason}）；兜底下单账号也不可用（{fb_detail}）"
                    # 落库：更新该商品下单失败原因（不累加尝试次数，账号恢复后下次自动重试）
                    await self._mark_no_account(pk, f"无可用下单账号：{reason}")
                    # 日志仅对每个监控任务打印一次，避免刷屏
                    if task_id not in warned_no_account_tasks:
                        warned_no_account_tasks.add(task_id)
                        logger.warning(
                            f"【{self.task_name}】监控任务「{task_name}」无可用账号跳过（含兜底），原因：{reason}"
                            f"（该任务剩余商品同因跳过，不再重复打印）"
                        )
                    continue

                result = await self._order_for_item(pk, item_id, order_candidates, disabled_accounts)
                if result == "ordered":
                    ordered += 1
                    ordered_item_ids.add(item_id)
                    task_done[task_id] = task_done.get(task_id, 0) + 1
                elif result == "no_account":
                    # 候选账号（含兜底）在实际下单调用中全部失效：记录原因，不累加尝试次数
                    skipped_no_account += 1
                    await self._mark_no_account(
                        pk, "无可用下单账号：任务账号与兜底账号在下单时全部失效（Session/Token过期、需重新登录或被风控）"
                    )
                else:
                    # failed：已实际尝试下单（render/create），计入该任务本次处理条数
                    failed += 1
                    task_done[task_id] = task_done.get(task_id, 0) + 1

                await asyncio.sleep(1)

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"【{self.task_name}】执行完成：待下单{len(items)}，成功{ordered}，"
                f"达批量上限跳过{skipped_batch_full}，无可用账号跳过{skipped_no_account}，"
                f"重复商品跳过{skipped_duplicate}，失败{failed}，"
                f"停用账号{len(disabled_accounts)}，耗时{elapsed:.2f}秒"
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"【{self.task_name}】执行异常: {exc}")

    async def _get_items_to_order(self) -> List[Tuple[int, str, int, Optional[str], Optional[int]]]:
        """查询未下单的采集商品（不再要求已私信）。

        Returns: (主键id, item_id, monitor_task_id, dm_account_id, owner_id) 列表
        """
        async with async_session_maker() as session:
            stmt = (
                select(
                    ListingMonitorItem.id,
                    ListingMonitorItem.item_id,
                    ListingMonitorItem.monitor_task_id,
                    ListingMonitorItem.dm_account_id,
                    ListingMonitorItem.owner_id,
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
            return [(r[0], r[1], r[2], r[3], r[4]) for r in rows]

    async def _owner_already_ordered(self, owner_id: Optional[int], item_id: str) -> bool:
        """判断同一用户下该商品是否已有下单成功记录（避免多任务采到同商品重复下单）。"""
        async with async_session_maker() as session:
            return await has_owner_ordered_item(session, owner_id, item_id)

    async def _mark_duplicate(self, pk: int) -> None:
        """将重复商品标记为已下单（duplicate），使其退出待下单查询，不再重复处理。"""
        try:
            async with async_session_maker() as session:
                item = (
                    await session.execute(
                        select(ListingMonitorItem).where(ListingMonitorItem.id == pk)
                    )
                ).scalar_one_or_none()
                if not item:
                    return
                item.is_ordered = True
                item.order_status = "duplicate"
                item.order_fail_reason = "同商品已在其他监控任务下单，跳过重复下单"
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"【{self.task_name}】标记重复商品失败 采集商品id={pk}：{exc}")

    async def _mark_no_account(self, pk: int, reason: str) -> None:
        """无可用账号时更新商品下单状态与失败原因。

        说明：账号不可用属于"环境问题"而非"商品问题"，故不累加 order_attempts，
        待账号恢复后下次任务可继续重试；仅更新 order_status/order_fail_reason 供前端查看。
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
                item.order_status = "no_account"
                item.order_fail_reason = str(reason)[:500] if reason else None
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"【{self.task_name}】更新无可用账号状态失败 采集商品id={pk}：{exc}")

    async def _load_task_accounts(self, task_id: int) -> Tuple[Dict[str, XYAccount], List[str], int, str, str, Optional[int]]:
        """加载监控任务配置的下单账号（过滤禁用/空Cookie/不存在的账号）。

        说明：不带启用/删除条件查询任务，以便停用、未配账号的任务也能取到关键字用于日志；
        任务删除/停用/未配账号时返回空账号字典与对应原因。
        
        Returns: (
            {account_id: XYAccount 仅可用账号},
            配置顺序的account_id列表,
            order_batch_size,
            任务名称(监控关键字),
            不可用原因明细(无则空串),
            任务所属分类ID(NULL=无分类),
        )
        """
        async with async_session_maker() as session:
            # 不带启用/删除条件查询，确保停用/未配账号的任务也能拿到关键字用于日志展示
            task = (
                await session.execute(
                    select(
                        ListingMonitorTask.keyword,
                        ListingMonitorTask.is_deleted,
                        ListingMonitorTask.is_enabled,
                        ListingMonitorTask.order_account_ids,
                        ListingMonitorTask.order_batch_size,
                        ListingMonitorTask.category_id,
                    ).where(ListingMonitorTask.id == task_id)
                )
            ).first()
            if not task:
                logger.warning(f"【{self.task_name}】监控任务 id={task_id} 不存在（可能已被物理删除）")
                return {}, [], 5, f"id={task_id}", "监控任务不存在", None
            keyword, is_deleted, is_enabled, order_account_ids_raw, order_batch_size, category_id = task
            task_name = keyword or f"id={task_id}"
            batch_size = order_batch_size if order_batch_size and order_batch_size > 0 else 5
            if is_deleted:
                logger.warning(f"【{self.task_name}】监控任务「{task_name}」已删除，跳过下单")
                return {}, [], batch_size, task_name, "监控任务已删除", category_id
            if not is_enabled:
                logger.warning(f"【{self.task_name}】监控任务「{task_name}」已停用，跳过下单")
                return {}, [], batch_size, task_name, "监控任务已停用", category_id
            account_ids = list(order_account_ids_raw or [])
            if not account_ids:
                logger.warning(
                    f"【{self.task_name}】监控任务「{task_name}」未配置下单账号(order_account_ids 为空)"
                )
                return {}, [], batch_size, task_name, "未配置下单账号(order_account_ids 为空)", category_id
            accounts_map, detail = await load_xy_accounts_by_ids(session, account_ids)

        logger.info(
            f"【{self.task_name}】监控任务「{task_name}」下单账号加载完成："
            f"配置{len(account_ids)}个，可用{len(accounts_map)}个"
            f"{('，不可用：' + detail) if detail else ''}"
            f"，每次最多下单{batch_size}条"
        )
        # 配置了账号但全部不可用，明细即为不可用原因
        return accounts_map, account_ids, batch_size, task_name, detail, category_id

    async def _load_fallback_accounts(
        self, owner_id: Optional[int], category_id: Optional[int] = None
    ) -> Tuple[Dict[str, XYAccount], str]:
        """加载生效的兜底下单账号（过滤禁用/空Cookie）。

        当监控任务自身无可用下单账号时回退使用，按 5 层链取：
        本用户·本分类 → 本用户·无分类 → 管理员·本分类 → 管理员·无分类。

        Returns: ({account_id: XYAccount 仅可用账号}, 不可用/未配置原因明细)
        """
        accounts_map, detail = await load_fallback_accounts(
            owner_id, category_id, log_prefix=self.task_name
        )
        logger.info(
            f"【{self.task_name}】用户{owner_id}(分类{category_id})兜底下单账号加载完成："
            f"可用{len(accounts_map)}个"
            f"{('，明细：' + detail) if detail else ''}"
        )
        if not accounts_map and not detail:
            detail = "兜底账号全部不可用"
        return accounts_map, detail

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

        策略：只要接口未返回成功就换下一个候选账号继续尝试。
        - account_invalid（Session/Token过期、需登录、风控）：全局停用该账号至本轮结束，换号；
        - 业务失败（商品不可买/缺地址/权限受限等）：换下一个候选账号继续尝试，但不全局停用该账号
          （可能仅该商品不可买，账号对其它商品仍可用）；
        - 全部候选账号都试过仍未成功：有业务失败则记录失败原因并累计尝试次数，返回 "failed"。

        Returns: "ordered" / "failed" / "no_account"
        """
        tried = 0
        had_business_failure = False
        last_fail_reason: Optional[str] = None
        for acc in accounts:
            if acc.account_id in disabled_accounts:
                continue
            tried += 1
            status, biz_order_id, fail_reason = await self._order_one(acc, item_id)
            if status == "success":
                # 记录实际下单成功的账号，供后续"采集商品发送私信"严格使用同一账号
                await self._record_result(pk, True, biz_order_id, None, account_id=acc.account_id)
                return "ordered"
            if status == "account_invalid":
                disabled_accounts.add(acc.account_id)
                logger.warning(
                    f"【{self.task_name}】账号 {acc.account_id} 下单不可用（{fail_reason}），"
                    f"本次停用，尝试下一个账号"
                )
                continue
            # 业务失败：换下一个候选账号继续尝试（不全局停用，可能仅该商品不可买）
            had_business_failure = True
            last_fail_reason = fail_reason
            logger.warning(
                f"【{self.task_name}】账号 {acc.account_id} 下单失败（{fail_reason}），尝试下一个账号"
            )
            continue

        # 所有候选账号都尝试过仍未成功
        if had_business_failure:
            await self._record_result(pk, False, None, last_fail_reason)
            return "failed"
        # 全部账号均为不可用且无任何账号实际尝试
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
        self,
        pk: int,
        ok: bool,
        biz_order_id: Optional[str],
        fail_reason: Optional[str],
        account_id: Optional[str] = None,
    ) -> None:
        """记录下单结果并累计尝试次数。

        - 成功：is_ordered=true（终态），记录 order_id 与下单账号 order_account_id；
        - 失败：is_ordered 保持 false，仅累计 order_attempts，达上限后由查询条件自动排除（停止重试）。

        Args:
            account_id: 本次下单成功使用的账号ID（供发送私信时严格使用同一账号）

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
                    item.ordered_at = get_beijing_now_naive()
                    if biz_order_id:
                        item.order_id = biz_order_id[:64]
                    # 记录下单账号，发送私信时严格使用该账号发起会话
                    if account_id:
                        item.order_account_id = account_id[:80]
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
