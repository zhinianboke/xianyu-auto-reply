"""
商品监控定时任务

功能：
1. 读取所有启用状态的商品监控任务（xy_listing_monitor_tasks）
2. 按监控类型确定搜索排序参数（上新=create/desc，降价=reduce/desc）
3. 使用监控任务关联账号的 Cookie 调用闲鱼搜索接口，按采集页数从第1页采集；
   某账号 Cookie 调用失败时自动切换下一个账号
4. 将采集商品 upsert 到采集商品信息表（xy_listing_monitor_items，与监控任务关联）
5. 每个监控任务执行后写入一条监控日志（xy_listing_monitor_logs），记录获取/新增/更新数
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from common.db.session import async_session_maker
from common.models.listing_monitor_item import ListingMonitorItem
from common.models.listing_monitor_log import ListingMonitorLog
from common.models.listing_monitor_task import ListingMonitorTask
from common.models.xy_account import XYAccount
from common.services.xianyu_search_client import XianyuSearchClient, parse_search_item
from common.utils.time_utils import BEIJING_TZ, get_beijing_now_naive

# 监控类型 -> (sortField, sortValue)
_MONITOR_SORT_MAP = {
    "listing": ("create", "desc"),   # 上新监控：按发布时间倒序
    "price_drop": ("reduce", "desc"),  # 降价监控：按降价排序
}

_INACTIVE_STATUSES = {"inactive", "disabled", "suspended", "deleted"}
_ROWS_PER_PAGE = 30

# 采集商品各字符串字段对应的列长度上限（与 xy_listing_monitor_items 表定义保持一致），
# 写库前按上限安全截断，避免超长值触发 MySQL DataError 导致整批回滚。
_ITEM_FIELD_LIMITS = {
    "title": 500,
    "price": 32,
    "area": 120,
    "pic_url": 1000,
    "seller_id": 120,
    "seller_nick": 120,
    "want_count": 32,
    "target_url": 1000,
}


def _truncate(value: Optional[str], max_len: int) -> Optional[str]:
    """将字符串安全截断到列长度上限，None 原样返回。"""
    if value is None:
        return None
    text = str(value)
    return text[:max_len] if len(text) > max_len else text


def _normalize_item_fields(parsed: dict) -> Dict[str, Optional[str]]:
    """按列长度上限截断采集商品的字符串字段。"""
    return {field: _truncate(parsed.get(field), limit) for field, limit in _ITEM_FIELD_LIMITS.items()}


def _ms_to_beijing_naive(publish_time_ms: Optional[str]) -> Optional[datetime]:
    """将毫秒时间戳字符串转换为北京时间（naive）。"""
    if not publish_time_ms:
        return None
    try:
        ms = int(publish_time_ms)
        if ms <= 0:
            return None
        return datetime.fromtimestamp(ms / 1000, tz=BEIJING_TZ).replace(tzinfo=None)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


class ListingMonitorTaskService:
    """商品监控定时任务服务"""

    def __init__(self, task_name: str = "商品监控任务"):
        self.task_name = task_name

    async def execute(self, force: bool = False):
        """执行商品监控任务：遍历所有启用的监控任务并采集。

        Args:
            force: 是否强制执行（手动触发时为 True，忽略每个任务自身的间隔）。
                   定时调度时为 False，仅执行"距上次执行已达到自身 interval_minutes"的任务。
        """
        logger.info(f"【{self.task_name}】开始执行（force={force}）")
        start_time = datetime.now()

        try:
            tasks = await self._get_enabled_tasks()
            if not tasks:
                logger.info(f"【{self.task_name}】没有启用的监控任务，结束")
                return

            # 按每个任务自身的间隔过滤出本次到期需要执行的任务
            now_naive = get_beijing_now_naive()
            due_tasks = [t for t in tasks if force or self._is_due(t, now_naive)]
            if not due_tasks:
                logger.info(f"【{self.task_name}】共 {len(tasks)} 个启用任务，本次无到期任务，结束")
                return

            logger.info(f"【{self.task_name}】启用任务 {len(tasks)} 个，本次执行 {len(due_tasks)} 个")
            for index, task in enumerate(due_tasks):
                try:
                    await self._process_task(task)
                except Exception as exc:  # noqa: BLE001
                    logger.error(f"【{self.task_name}】监控任务 {task.id} 执行异常: {exc}")
                # 任务间隔，避免请求过密
                if index != len(due_tasks) - 1:
                    await asyncio.sleep(2)

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"【{self.task_name}】执行完成，共处理 {len(due_tasks)} 个监控任务，耗时 {elapsed:.2f}秒")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"【{self.task_name}】执行异常: {exc}")

    @staticmethod
    def _is_due(task: ListingMonitorTask, now_naive: datetime) -> bool:
        """根据任务自身的 interval_minutes 判断是否到期需要执行。"""
        if task.last_run_at is None:
            return True
        last_run = task.last_run_at
        if last_run.tzinfo is not None:
            last_run = last_run.replace(tzinfo=None)
        interval_minutes = task.interval_minutes if task.interval_minutes and task.interval_minutes > 0 else 1
        elapsed_seconds = (now_naive - last_run).total_seconds()
        return elapsed_seconds >= interval_minutes * 60

    async def _get_enabled_tasks(self) -> List[ListingMonitorTask]:
        """读取所有启用、未删除的监控任务。"""
        async with async_session_maker() as session:
            stmt = select(ListingMonitorTask).where(
                ListingMonitorTask.is_deleted.is_(False),
                ListingMonitorTask.is_enabled.is_(True),
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def _load_accounts(self, account_ids: List[str]) -> List[XYAccount]:
        """按监控任务配置的账号ID列表加载可用账号（保持配置顺序、过滤禁用）。"""
        if not account_ids:
            return []
        async with async_session_maker() as session:
            stmt = select(XYAccount).where(XYAccount.account_id.in_(account_ids))
            rows = list((await session.execute(stmt)).scalars().all())
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

    async def _get_account_usage_rank(self, task_id: int, limit: int = 10) -> Dict[str, int]:
        """统计该监控任务最近 limit 条日志中各账号的"使用新近度"。

        Returns:
            account_id -> 最近一次被使用的日志序号（0=最新一条；数值越小表示越近期使用）。
            未出现在最近日志中的账号不在返回字典中（视为最久未使用）。
        """
        rank: Dict[str, int] = {}
        async with async_session_maker() as session:
            stmt = (
                select(ListingMonitorLog.account_id, ListingMonitorLog.used_account_ids)
                .where(ListingMonitorLog.monitor_task_id == task_id)
                .order_by(ListingMonitorLog.id.desc())
                .limit(limit)
            )
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

    async def _process_task(self, task: ListingMonitorTask):
        """处理单个监控任务：采集 + 入库 + 写日志 + 更新执行时间。"""
        sort_field, sort_value = _MONITOR_SORT_MAP.get(task.monitor_type, _MONITOR_SORT_MAP["listing"])
        accounts = await self._load_accounts(list(task.account_ids or []))

        # 负载均衡：优先使用最近未被使用过的账号；
        # 全部都用过时，按"上次使用越久远越优先"轮换（避免固定使用同一个账号）。
        if accounts:
            usage_rank = await self._get_account_usage_rank(task.id, limit=10)
            if usage_rank:
                _stalest = len(accounts) + 100  # 未出现在最近日志中的账号视为最久未使用，优先级最高
                accounts = sorted(
                    accounts,
                    key=lambda a: usage_rank.get(a.account_id, _stalest),
                    reverse=True,
                )

        used_account_id: Optional[str] = None
        used_account_ids: set[str] = set()
        status = "success"
        message = ""
        all_items: List[dict] = []
        pages_collected = 0

        if not accounts:
            status = "failed"
            message = "无可用账号（账号不存在/禁用/Cookie为空）"
            logger.warning(f"【{self.task_name}】监控任务 {task.id}({task.keyword}) {message}")
        else:
            price_min = float(task.price_min) if task.price_min is not None else None
            price_max = float(task.price_max) if task.price_max is not None else None
            working_idx = 0
            page_failed = False

            for page in range(1, max(task.collect_pages, 1) + 1):
                page_result = None
                # 从上次成功的账号开始，逐个尝试，成功即止
                for offset in range(len(accounts)):
                    idx = (working_idx + offset) % len(accounts)
                    acc = accounts[idx]
                    client = XianyuSearchClient(acc.account_id, acc.cookie)
                    res = await client.search(
                        keyword=task.keyword,
                        page_number=page,
                        sort_field=sort_field,
                        sort_value=sort_value,
                        rows_per_page=_ROWS_PER_PAGE,
                        price_min=price_min,
                        price_max=price_max,
                    )
                    if res.get("success"):
                        working_idx = idx
                        used_account_id = acc.account_id
                        used_account_ids.add(acc.account_id)
                        page_result = res
                        break
                    logger.warning(
                        f"【{self.task_name}】任务 {task.id} 第{page}页 账号 {acc.account_id} 调用失败: {res.get('error')}，尝试下一个账号"
                    )

                if not page_result:
                    page_failed = True
                    message = f"第{page}页所有账号调用失败"
                    logger.warning(f"【{self.task_name}】监控任务 {task.id} {message}")
                    break

                pages_collected += 1
                for entry in page_result.get("items", []):
                    parsed = parse_search_item(entry)
                    if parsed:
                        all_items.append(parsed)

                # 没有下一页则提前结束
                if not page_result.get("has_next_page"):
                    break
                await asyncio.sleep(1)

            if page_failed:
                status = "partial" if pages_collected > 0 else "failed"

        fetched_count = len(all_items)
        inserted_count, updated_count = await self._upsert_items(task, all_items)

        if status == "success" and not message:
            message = f"采集{pages_collected}页，获取{fetched_count}，新增{inserted_count}，更新{updated_count}"

        await self._write_log(
            task=task,
            account_id=used_account_id,
            used_account_ids=sorted(used_account_ids),
            pages=pages_collected,
            fetched=fetched_count,
            inserted=inserted_count,
            updated=updated_count,
            status=status,
            message=message,
        )
        await self._update_last_run(task.id)

        logger.info(
            f"【{self.task_name}】任务 {task.id}({task.keyword}/{task.monitor_type}) 完成："
            f"账号={used_account_id}，页数={pages_collected}，获取={fetched_count}，新增={inserted_count}，更新={updated_count}，状态={status}"
        )

    async def _upsert_items(self, task: ListingMonitorTask, items: List[dict]) -> tuple[int, int]:
        """将采集商品 upsert 到采集商品表，返回 (新增数, 更新数)。"""
        if not items:
            return 0, 0

        # 按 item_id 去重（同一次采集多页可能重复），保留最后一次出现的数据
        dedup: Dict[str, dict] = {}
        for it in items:
            dedup[it["item_id"]] = it

        now = get_beijing_now_naive()
        inserted = 0
        updated = 0

        async with async_session_maker() as session:
            item_ids = list(dedup.keys())
            existing_stmt = select(ListingMonitorItem).where(
                ListingMonitorItem.monitor_task_id == task.id,
                ListingMonitorItem.item_id.in_(item_ids),
            )
            existing_rows = (await session.execute(existing_stmt)).scalars().all()
            existing_map = {row.item_id: row for row in existing_rows}

            for item_id, parsed in dedup.items():
                publish_time = _ms_to_beijing_naive(parsed.get("publish_time_ms"))
                raw_json = self._dump_raw(parsed.get("raw_main"))
                fields = _normalize_item_fields(parsed)
                row = existing_map.get(item_id)
                if row:
                    row.title = fields["title"]
                    row.price = fields["price"]
                    row.area = fields["area"]
                    row.pic_url = fields["pic_url"]
                    row.seller_id = fields["seller_id"]
                    row.seller_nick = fields["seller_nick"]
                    row.want_count = fields["want_count"]
                    if publish_time is not None:
                        row.publish_time = publish_time
                    row.target_url = fields["target_url"]
                    row.raw_json = raw_json
                    row.last_seen_at = now
                    updated += 1
                else:
                    session.add(
                        ListingMonitorItem(
                            monitor_task_id=task.id,
                            owner_id=task.owner_id,
                            item_id=item_id,
                            title=fields["title"],
                            price=fields["price"],
                            area=fields["area"],
                            pic_url=fields["pic_url"],
                            seller_id=fields["seller_id"],
                            seller_nick=fields["seller_nick"],
                            want_count=fields["want_count"],
                            publish_time=publish_time,
                            target_url=fields["target_url"],
                            raw_json=raw_json,
                            last_seen_at=now,
                        )
                    )
                    inserted += 1

            await session.commit()
        return inserted, updated

    @staticmethod
    def _dump_raw(raw_main) -> Optional[str]:
        """将原始商品数据序列化为 JSON 字符串（兜底存储）。

        TEXT 列上限约 64KB，超长时放弃存储原始数据（返回 None），避免触发 DataError 导致整批回滚。
        """
        if not raw_main:
            return None
        try:
            dumped = json.dumps(raw_main, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            return None
        if len(dumped.encode("utf-8")) > 60000:
            return None
        return dumped

    async def _write_log(
        self,
        task: ListingMonitorTask,
        account_id: Optional[str],
        used_account_ids: List[str],
        pages: int,
        fetched: int,
        inserted: int,
        updated: int,
        status: str,
        message: str,
    ):
        """写入一条监控执行日志。"""
        async with async_session_maker() as session:
            session.add(
                ListingMonitorLog(
                    monitor_task_id=task.id,
                    owner_id=task.owner_id,
                    monitor_type=task.monitor_type,
                    keyword=task.keyword,
                    account_id=account_id,
                    used_account_ids=list(used_account_ids or []),
                    pages=pages,
                    fetched_count=fetched,
                    inserted_count=inserted,
                    updated_count=updated,
                    status=status,
                    message=(message or "")[:1000],
                )
            )
            await session.commit()

    async def _update_last_run(self, task_id: int):
        """更新监控任务最近执行时间。"""
        async with async_session_maker() as session:
            task = (
                await session.execute(
                    select(ListingMonitorTask).where(ListingMonitorTask.id == task_id)
                )
            ).scalar_one_or_none()
            if task:
                task.last_run_at = get_beijing_now_naive()
                await session.commit()


# 全局实例
listing_monitor_task_service = ListingMonitorTaskService(task_name="商品监控任务")
