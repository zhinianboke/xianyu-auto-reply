"""
采集商品卖家ID补全定时任务

功能：
1. 查询采集商品表中卖家真实ID（seller_user_id）为空、且当天或昨天采集入库（created_at >= 昨天00:00）、
   且下单状态为「未下单/已下单/下单失败/无可用账号」（排除重复 duplicate）的数据
2. 调用商品详情接口补全卖家真实ID与商品详情
3. Cookie 账号来源与采集任务一致：监控任务配置的采集账号 + 用户级兜底采集账号，
   用户未配置时回退管理员全局兜底；任务账号在前、兜底在后、去重保序，轮换使用。
   与下单任务一致：监控任务被删除/停用也不影响补全——任务账号取不到时按商品归属用户的兜底采集账号补全
4. 与采集任务一致的账号负载与风控规避：按最近使用度（跨任务监控日志）排序，优先选用
   最近未使用的账号；过滤处于风控冷却期的账号；账号触发风控时加入冷却并停用本轮
5. 若某账号接口返回不可用（Session/Token过期、需登录、风控等），本次运行不再使用该账号，
   等下次任务启动时再重新使用

说明：
- 当天+昨天窗口：提供约24小时容错窗口，避免定时任务短期故障导致商品永久卡在未补全状态；
  早于昨天的遗留数据不再处理，防止历史脏数据持续占用补全配额。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import and_, or_, select

from common.db.session import async_session_maker
from common.models.listing_monitor_item import ListingMonitorItem
from common.models.listing_monitor_log import ListingMonitorLog
from common.models.listing_monitor_task import ListingMonitorTask
from common.models.xy_account import XYAccount
from common.services.account_cooldown import DEFAULT_COOLDOWN_SECONDS, account_cooldown_manager
from common.services.collect_account_loader import merge_task_and_fallback_account_ids
from common.services.xianyu_detail_client import XianyuItemDetailClient
from common.services.xianyu_mtop import fetch_proxy_from_api
from common.utils.time_utils import get_beijing_now_naive

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
            # 任务ID -> 实际代理URL（本轮该任务复用，None=直连）
            task_proxy_cache: Dict[int, Optional[str]] = {}
            # 任务ID -> 轮换指针（让同一任务的多条商品轮换使用不同账号）
            task_rr: Dict[int, int] = {}
            # 本次运行被判定不可用的账号（停用至本次结束）
            disabled_accounts: set[str] = set()

            filled = 0
            item_failed = 0
            no_account = 0

            for pk, item_id, task_id, item_owner_id in items:
                accounts = task_accounts_cache.get(task_id)
                if accounts is None:
                    accounts, proxy_api, owner_id = await self._load_task_accounts(task_id, item_owner_id)
                    # 跨任务 usage-rank 负载均衡：优先选用最近未使用的账号（与采集任务一致）
                    if accounts:
                        usage_rank = await self._get_account_usage_rank(owner_id, limit=40)
                        if usage_rank:
                            _stalest = 10 ** 9  # 未出现在最近日志中的账号视为最久未使用，优先级最高
                            accounts = sorted(
                                accounts,
                                key=lambda a: usage_rank.get(a.account_id, _stalest),
                                reverse=True,
                            )
                    # 风控冷却过滤：去掉处于冷却期（被挤爆/触发验证后冷却时长内）的账号（与采集任务一致）
                    if accounts:
                        available_ids = set(
                            account_cooldown_manager.filter_available([a.account_id for a in accounts])
                        )
                        accounts = [a for a in accounts if a.account_id in available_ids]
                        if not accounts:
                            logger.warning(
                                f"【{self.task_name}】任务 {task_id} 所有可用账号均在风控冷却期，本次跳过补全"
                            )
                    task_accounts_cache[task_id] = accounts
                    # 任务配置了代理API地址时，取一个HTTP代理供本任务本轮使用（失败则直连）
                    task_proxy_cache[task_id] = (
                        await fetch_proxy_from_api(proxy_api, account_id=str(task_id)) if proxy_api else None
                    )

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
                    proxy=task_proxy_cache.get(task_id),
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

    async def _get_items_to_fill(self) -> List[Tuple[int, str, int, Optional[int]]]:
        """查询卖家真实ID为空的采集商品（当天和昨天入库的），返回 (主键id, item_id, monitor_task_id, owner_id) 列表。

        说明：只补全当天和昨天采集入库（created_at >= 北京时间昨天 00:00）的商品，
        提供约 24 小时容错窗口，避免定时任务短期故障导致商品永久卡在未补全状态；
        早于昨天的遗留数据不再处理，防止历史脏数据持续占用补全配额。

        下单状态过滤：仅补全下单状态为「未下单(NULL)/已下单(success)/下单失败(failed)/
        无可用账号(no_account)」的商品；排除「重复(duplicate)」——重复商品已被同用户其他
        监控任务下单，无需再补全卖家详情。
        """
        # 北京时间今天 00:00 前推 1 天作为下限（即昨天 00:00，覆盖当天和昨天）
        cutoff_time = get_beijing_now_naive().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        async with async_session_maker() as session:
            stmt = (
                select(
                    ListingMonitorItem.id,
                    ListingMonitorItem.item_id,
                    ListingMonitorItem.monitor_task_id,
                    ListingMonitorItem.owner_id,
                )
                .where(
                    and_(
                        # 仅处理当天和昨天入库的商品
                        ListingMonitorItem.created_at >= cutoff_time,
                        or_(
                            ListingMonitorItem.seller_user_id.is_(None),
                            ListingMonitorItem.seller_user_id == "",
                        ),
                        # 排除已明确失败、不再补全的商品（如跨境商品/已下架）
                        or_(
                            ListingMonitorItem.seller_fill_status.is_(None),
                            ListingMonitorItem.seller_fill_status != "failed",
                        ),
                        # 仅补全下单状态为 未下单(NULL)/已下单/下单失败/无可用账号 的商品，排除重复(duplicate)
                        or_(
                            ListingMonitorItem.order_status.is_(None),
                            ListingMonitorItem.order_status.in_(["success", "failed", "no_account"]),
                        ),
                    )
                )
                .order_by(ListingMonitorItem.id.asc())
                .limit(_MAX_ITEMS_PER_RUN)
            )
            rows = (await session.execute(stmt)).all()
            return [(r[0], r[1], r[2], r[3]) for r in rows]

    async def _load_task_accounts(
        self, task_id: int, item_owner_id: Optional[int]
    ) -> Tuple[List[XYAccount], Optional[str], Optional[int]]:
        """加载补全可用账号、代理API地址与归属用户ID（保持顺序、过滤禁用/空Cookie）。

        与下单任务对齐：不因监控任务被删除/停用而放弃补全。
        - 任务存在（含已删除/已停用）：取其采集账号(account_ids) + 兜底采集账号，归属用户取任务 owner_id；
        - 任务查不到：归属用户回退为商品自身 owner_id，仅按兜底采集账号补全。
        兜底覆盖链：本用户·本分类→本用户·无分类→管理员·本分类→管理员·无分类；任务账号在前、兜底在后、去重保序。

        Returns: (可用账号列表, 代理API地址或None, 归属用户ID或None)
        """
        async with async_session_maker() as session:
            # 不过滤 is_deleted/is_enabled：监控任务被软删除/停用后，仍按兜底采集账号继续补全（与下单任务一致）
            task = (
                await session.execute(
                    select(ListingMonitorTask).where(ListingMonitorTask.id == task_id)
                )
            ).scalar_one_or_none()
            if task:
                proxy_api = task.proxy_url
                owner_id = task.owner_id if task.owner_id is not None else item_owner_id
                category_id = task.category_id
                task_account_ids = list(task.account_ids or [])
            else:
                # 任务查不到（极端情况）：完全回退兜底，归属用户取商品自身 owner_id
                proxy_api = None
                owner_id = item_owner_id
                category_id = None
                task_account_ids = []
            # 合并任务采集账号 + 生效兜底采集账号（任务账号为空时即纯兜底）
            account_ids = await merge_task_and_fallback_account_ids(
                session, task_account_ids, owner_id, category_id
            )
            if not account_ids:
                logger.warning(
                    f"【{self.task_name}】任务 {task_id}（用户 {owner_id}）未配置任何采集账号"
                    f"（任务账号与兜底采集账号均为空），该任务名下商品本轮跳过补全"
                )
                return [], proxy_api, owner_id
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
        if not ordered:
            logger.warning(
                f"【{self.task_name}】任务 {task_id}（用户 {owner_id}）合并采集账号共 {len(account_ids)} 个，"
                f"但均不可用（Cookie为空/账号已停用），该任务名下商品本轮跳过补全"
            )
        return ordered, proxy_api, owner_id

    async def _get_account_usage_rank(self, owner_id: Optional[int], limit: int = 40) -> Dict[str, int]:
        """统计该用户最近 limit 条监控日志（跨任务）中各账号的"使用新近度"。

        与采集任务共用监控日志(ListingMonitorLog)的账号使用记录，使补全任务优先选用
        最近未被采集使用的账号，跨任务均衡账号负载、规避风控。仅按归属用户隔离，不限具体任务。

        Returns:
            account_id -> 最近一次被使用的日志序号（0=最新一条；数值越小表示越近期使用）。
            未出现在最近日志中的账号不在返回字典中（视为最久未使用，优先使用）。
        """
        rank: Dict[str, int] = {}
        async with async_session_maker() as session:
            stmt = (
                select(ListingMonitorLog.account_id, ListingMonitorLog.used_account_ids)
                .order_by(ListingMonitorLog.id.desc())
                .limit(limit)
            )
            if owner_id is not None:
                stmt = stmt.where(ListingMonitorLog.owner_id == owner_id)
            for idx, (account_id, used_ids) in enumerate((await session.execute(stmt)).all()):
                candidates = list(used_ids or [])
                if account_id:
                    candidates.append(account_id)
                for aid in candidates:
                    if aid:
                        aid = str(aid)
                        # 只记录最近一次（最小 idx），后续更旧的日志不覆盖
                        if aid not in rank:
                            rank[aid] = idx
        return rank

    async def _fill_one_item(
        self,
        pk: int,
        item_id: str,
        accounts: List[XYAccount],
        rr_start: int,
        disabled_accounts: set[str],
        proxy: Optional[str] = None,
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
            client = XianyuItemDetailClient(acc.account_id, acc.cookie, owner_id=acc.owner_id, proxy=proxy)
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
                # 风控类错误（被挤爆/触发验证）额外加入冷却，避免后续任务短时再用该账号触发风控
                if account_cooldown_manager.is_risk_control_error(result.get("error")):
                    account_cooldown_manager.add(acc.account_id)
                    logger.warning(
                        f"【{self.task_name}】账号 {acc.account_id} 触发风控（{result.get('error')}），"
                        f"加入冷却 {DEFAULT_COOLDOWN_SECONDS // 60} 分钟并停用本轮，尝试下一个账号"
                    )
                else:
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
