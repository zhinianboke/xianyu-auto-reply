"""
采集商品卖家ID补全定时任务

功能：
1. 查询采集商品表中卖家真实ID（seller_user_id）为空的数据
2. 调用商品详情接口补全卖家真实ID与商品详情
3. Cookie 使用该商品对应监控任务里配置的账号，轮换使用这些账号
4. 若某账号接口返回不可用（Session/Token过期、需登录、风控等），本次运行不再使用该账号，
   等下次任务启动时再重新使用
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import and_, or_, select

from common.db.session import async_session_maker
from common.models.listing_monitor_item import ListingMonitorItem
from common.models.listing_monitor_task import ListingMonitorTask
from common.models.xy_account import XYAccount
from common.services.xianyu_detail_client import XianyuItemDetailClient

_INACTIVE_STATUSES = {"inactive", "disabled", "suspended", "deleted"}
# 单次任务最多处理的待补全商品数，避免单次运行过久
_MAX_ITEMS_PER_RUN = 300
# detail_json 最大存储字节数（MEDIUMTEXT 上限 16MB，留足余量）
_MAX_DETAIL_BYTES = 10 * 1024 * 1024


class SellerFillTaskService:
    """采集商品卖家ID补全任务服务"""

    def __init__(self, task_name: str = "采集商品卖家ID补全"):
        self.task_name = task_name

    async def execute(self):
        """执行卖家ID补全任务。"""
        logger.info(f"【{self.task_name}】开始执行")
        start_time = datetime.now()

        try:
            items = await self._get_items_to_fill()
            if not items:
                logger.info(f"【{self.task_name}】没有待补全卖家ID的商品，结束")
                return

            logger.info(f"【{self.task_name}】查询到 {len(items)} 条待补全商品")

            # 任务ID -> 该任务可用账号列表（缓存，避免重复查询）
            task_accounts_cache: Dict[int, List[XYAccount]] = {}
            # 任务ID -> 轮换指针（让同一任务的多条商品轮换使用不同账号）
            task_rr: Dict[int, int] = {}
            # 本次运行被判定不可用的账号（停用至本次结束）
            disabled_accounts: set[str] = set()

            filled = 0
            item_failed = 0
            no_account = 0

            for pk, item_id, task_id in items:
                accounts = task_accounts_cache.get(task_id)
                if accounts is None:
                    accounts = await self._load_task_accounts(task_id)
                    task_accounts_cache[task_id] = accounts

                usable = [a for a in accounts if a.account_id not in disabled_accounts]
                if not usable:
                    no_account += 1
                    continue

                result = await self._fill_one_item(
                    pk=pk,
                    item_id=item_id,
                    accounts=usable,
                    rr_start=task_rr.get(task_id, 0),
                    disabled_accounts=disabled_accounts,
                )
                # 轮换指针前移
                task_rr[task_id] = task_rr.get(task_id, 0) + 1

                if result == "filled":
                    filled += 1
                elif result == "no_account":
                    no_account += 1
                else:
                    item_failed += 1

                await asyncio.sleep(0.3)

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"【{self.task_name}】执行完成：待补全{len(items)}，成功{filled}，"
                f"商品失败{item_failed}，无可用账号{no_account}，停用账号{len(disabled_accounts)}，耗时{elapsed:.2f}秒"
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"【{self.task_name}】执行异常: {exc}")

    async def _get_items_to_fill(self) -> List[Tuple[int, str, int]]:
        """查询卖家真实ID为空的采集商品，返回 (主键id, item_id, monitor_task_id) 列表。"""
        async with async_session_maker() as session:
            stmt = (
                select(
                    ListingMonitorItem.id,
                    ListingMonitorItem.item_id,
                    ListingMonitorItem.monitor_task_id,
                )
                .where(
                    and_(
                        or_(
                            ListingMonitorItem.seller_user_id.is_(None),
                            ListingMonitorItem.seller_user_id == "",
                        ),
                        # 排除已明确失败、不再补全的商品（如跨境商品/已下架）
                        or_(
                            ListingMonitorItem.seller_fill_status.is_(None),
                            ListingMonitorItem.seller_fill_status != "failed",
                        ),
                    )
                )
                .order_by(ListingMonitorItem.id.asc())
                .limit(_MAX_ITEMS_PER_RUN)
            )
            rows = (await session.execute(stmt)).all()
            return [(r[0], r[1], r[2]) for r in rows]

    async def _load_task_accounts(self, task_id: int) -> List[XYAccount]:
        """加载监控任务配置的可用账号（任务须未删除且启用；保持配置顺序、过滤禁用/空Cookie）。"""
        async with async_session_maker() as session:
            task = (
                await session.execute(
                    select(ListingMonitorTask).where(
                        ListingMonitorTask.id == task_id,
                        ListingMonitorTask.is_deleted.is_(False),
                        ListingMonitorTask.is_enabled.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if not task:
                return []
            account_ids = list(task.account_ids or [])
            if not account_ids:
                return []
            rows = list(
                (
                    await session.execute(
                        select(XYAccount).where(XYAccount.account_id.in_(account_ids))
                    )
                ).scalars().all()
            )

        by_id = {row.account_id: row for row in rows}
        ordered: List[XYAccount] = []
        for account_id in account_ids:
            acc = by_id.get(account_id)
            if not acc or not acc.cookie:
                continue
            if (acc.status or "active").strip().lower() in _INACTIVE_STATUSES:
                continue
            ordered.append(acc)
        return ordered

    async def _fill_one_item(
        self,
        pk: int,
        item_id: str,
        accounts: List[XYAccount],
        rr_start: int,
        disabled_accounts: set[str],
    ) -> str:
        """补全单个商品的卖家ID与详情。

        Returns: "filled" / "item_failed" / "no_account"
        """
        n = len(accounts)
        tried = 0
        for offset in range(n):
            acc = accounts[(rr_start + offset) % n]
            if acc.account_id in disabled_accounts:
                continue
            tried += 1
            client = XianyuItemDetailClient(acc.account_id, acc.cookie, owner_id=acc.owner_id)
            result = await client.get_detail(item_id)
            # 令牌可能已刷新：回写内存账号Cookie，供同账号后续商品复用
            acc.cookie = client.cookies_str

            if result.get("success"):
                await self._save_detail(pk, result)
                logger.info(
                    f"【{self.task_name}】商品 {item_id} 补全成功："
                    f"卖家ID={result.get('seller_user_id')}（账号 {acc.account_id}）"
                )
                return "filled"

            if result.get("account_invalid"):
                disabled_accounts.add(acc.account_id)
                logger.warning(
                    f"【{self.task_name}】账号 {acc.account_id} 不可用（{result.get('error')}），"
                    f"本次停用，尝试下一个账号"
                )
                continue

            if result.get("item_invalid"):
                # 商品级明确失败（跨境商品/下架/不存在等）：记录失败原因并标记不再补全
                reason = result.get("error")
                await self._mark_failed(pk, reason)
                logger.info(
                    f"【{self.task_name}】商品 {item_id} 详情获取失败（账号 {acc.account_id}）：{reason}，已标记不再补全"
                )
                return "item_failed"

            # 临时失败（网络异常/重试耗尽等）：不标记，换下一个账号重试，留待本轮其他账号或下次任务
            logger.info(
                f"【{self.task_name}】商品 {item_id} 临时获取失败（账号 {acc.account_id}）：{result.get('error')}，尝试下一个账号"
            )
            continue

        # 所有账号都被停用
        return "no_account" if tried == 0 else "item_failed"

    async def _save_detail(self, pk: int, result: dict) -> None:
        """将补全结果写回采集商品记录。"""
        seller_user_id = result.get("seller_user_id")
        seller_nick = result.get("seller_nick")
        detail = result.get("detail")
        detail_json = self._dump_detail(detail)

        async with async_session_maker() as session:
            item = (
                await session.execute(
                    select(ListingMonitorItem).where(ListingMonitorItem.id == pk)
                )
            ).scalar_one_or_none()
            if not item:
                return
            if seller_user_id:
                item.seller_user_id = seller_user_id[:64]
            if seller_nick:
                item.seller_nick = seller_nick[:120]
            if detail_json is not None:
                item.detail_json = detail_json
            await session.commit()

    async def _mark_failed(self, pk: int, reason) -> None:
        """记录卖家ID补全的明确业务失败原因，并标记后续不再补全。"""
        async with async_session_maker() as session:
            item = (
                await session.execute(
                    select(ListingMonitorItem).where(ListingMonitorItem.id == pk)
                )
            ).scalar_one_or_none()
            if not item:
                return
            item.seller_fill_status = "failed"
            item.seller_fill_fail_reason = str(reason)[:500] if reason else None
            await session.commit()

    @staticmethod
    def _dump_detail(detail) -> Optional[str]:
        """序列化商品详情为 JSON 字符串，超大时放弃存储以避免写入失败。"""
        if not detail:
            return None
        try:
            dumped = json.dumps(detail, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            return None
        if len(dumped.encode("utf-8")) > _MAX_DETAIL_BYTES:
            return None
        return dumped


# 全局实例
seller_fill_task_service = SellerFillTaskService(task_name="采集商品卖家ID补全")
