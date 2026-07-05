"""
公共商品上新监控任务服务

功能：
1. 提供上新监控任务的分页查询与维护能力
2. 处理多用户数据隔离（owner_id）与软删除（is_deleted）
3. 校验关键字、价格区间、任务间隔、账号列表等业务规则
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger
from sqlalchemy import case, delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.listing_monitor_task import ListingMonitorTask
from common.models.listing_monitor_item import ListingMonitorItem
from common.models.listing_monitor_log import ListingMonitorLog
from common.models.listing_monitor_category import ListingMonitorCategory
from common.models.xy_account import XYAccount
from common.models.user import User
from common.utils.time_utils import get_beijing_now_naive, safe_isoformat

# 合法分页大小
_VALID_PAGE_SIZES = (10, 20, 50, 100)

# 合法监控类型：listing-上新监控，price_drop-降价监控
_VALID_MONITOR_TYPES = ("listing", "price_drop")

# 监控日志保留天数：清空日志与定时自动清理均只删除该天数之前的数据
LOG_RETENTION_DAYS = 10


def _to_decimal(value: Any) -> Optional[Decimal]:
    """将输入安全转换为两位小数的 Decimal，空值返回 None。"""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("价格格式不正确")


def _parse_naive_datetime(value: Optional[str]) -> Optional[datetime]:
    """将前端传入的时间字符串解析为 naive 北京时间，用于采集时间区间过滤。

    兼容 "2026-06-18T22:36"、"2026-06-18T22:36:00"、"2026-06-18 22:36:00" 等格式；
    解析失败或空值返回 None（即不施加该边界条件）。
    """
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    normalized = raw.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def _safe_json_loads(text: Optional[str]) -> Any:
    """安全解析 JSON 字符串，失败或空返回 None。"""
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _task_to_dict(task: ListingMonitorTask) -> Dict[str, Any]:
    """将监控任务模型转换为前端可用的字典。"""
    return {
        "id": task.id,
        "owner_id": task.owner_id,
        "category_id": task.category_id,
        "monitor_type": task.monitor_type,
        "keyword": task.keyword,
        "price_min": float(task.price_min) if task.price_min is not None else None,
        "price_max": float(task.price_max) if task.price_max is not None else None,
        "publish_days": task.publish_days,
        "interval_minutes": task.interval_minutes,
        "collect_pages": task.collect_pages,
        "proxy_url": task.proxy_url,
        "account_ids": list(task.account_ids or []),
        "order_account_ids": list(task.order_account_ids or []),
        "dm_content": task.dm_content,
        "dm_batch_size": task.dm_batch_size,
        "order_batch_size": task.order_batch_size,
        "direct_order": bool(task.direct_order),
        "is_enabled": bool(task.is_enabled),
        "last_run_at": safe_isoformat(task.last_run_at),
        "remark": task.remark,
        "created_at": safe_isoformat(task.created_at),
        "updated_at": safe_isoformat(task.updated_at),
    }


def _log_to_dict(log: ListingMonitorLog) -> Dict[str, Any]:
    """将监控日志模型转换为前端可用的字典。"""
    return {
        "id": log.id,
        "monitor_task_id": log.monitor_task_id,
        "monitor_type": log.monitor_type,
        "keyword": log.keyword,
        "trigger_type": log.trigger_type,
        "account_id": log.account_id,
        "used_account_ids": list(log.used_account_ids or []),
        "pages": log.pages,
        "fetched_count": log.fetched_count,
        "inserted_count": log.inserted_count,
        "updated_count": log.updated_count,
        "status": log.status,
        "message": log.message,
        "created_at": safe_isoformat(log.created_at),
    }


def _item_to_dict(item: ListingMonitorItem, task_keyword: Optional[str] = None) -> Dict[str, Any]:
    """将采集商品模型转换为前端可用的字典。

    task_keyword: 所属监控任务的关键字（任务名称），由调用方批量查出后传入。
    """
    return {
        "id": item.id,
        "monitor_task_id": item.monitor_task_id,
        "monitor_task_keyword": task_keyword,
        "item_id": item.item_id,
        "title": item.title,
        "price": item.price,
        "area": item.area,
        "pic_url": item.pic_url,
        "seller_id": item.seller_id,
        "seller_user_id": item.seller_user_id,
        "seller_nick": item.seller_nick,
        "seller_avatar": item.seller_avatar,
        "want_count": item.want_count,
        "tags": item.tags,
        "publish_time": safe_isoformat(item.publish_time),
        "target_url": item.target_url,
        "has_detail": bool(item.detail_json),
        "seller_fill_status": item.seller_fill_status,
        "seller_fill_fail_reason": item.seller_fill_fail_reason,
        "is_dm_sent": bool(item.is_dm_sent),
        "dm_account_id": item.dm_account_id,
        "dm_chat_id": item.dm_chat_id,
        "dm_status": item.dm_status,
        "dm_fail_reason": item.dm_fail_reason,
        "dm_attempts": item.dm_attempts,
        "is_ordered": bool(item.is_ordered),
        "order_id": item.order_id,
        "order_account_id": item.order_account_id,
        "order_status": item.order_status,
        "order_fail_reason": item.order_fail_reason,
        "order_attempts": item.order_attempts,
        "ordered_at": safe_isoformat(item.ordered_at),
        "last_seen_at": safe_isoformat(item.last_seen_at),
        "created_at": safe_isoformat(item.created_at),
        "updated_at": safe_isoformat(item.updated_at),
    }


class ListingMonitorService:
    """商品上新监控任务服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _resolve_category(
        self, owner_id: Optional[int], category_id: int
    ) -> ListingMonitorCategory:
        """校验分类存在且当前用户有权使用。

        普通用户只能使用自己创建的分类；管理员（owner_id=None）可使用任意分类。
        与分类列表的隔离规则保持一致，防止普通用户通过构造请求挂用他人分类。

        Args:
            owner_id: 数据隔离范围。None=管理员（不限制归属）；非 None 仅限本人创建的分类
            category_id: 分类ID

        Returns:
            校验通过的分类对象

        Raises:
            ValueError: 分类不存在、已删除或无权限使用
        """
        category = await self.session.get(ListingMonitorCategory, category_id)
        if not category or category.is_deleted:
            raise ValueError("所选分类不存在")
        # 普通用户只能使用自己创建的分类；管理员不受限
        if owner_id is not None and category.owner_id != owner_id:
            raise ValueError("所选分类不存在或无权限使用")
        return category

    async def _normalize_payload(self, owner_id: Optional[int], data: dict, partial: bool) -> Dict[str, Any]:
        """校验并规整请求数据。partial=True 时仅处理传入的字段（用于更新）。"""
        payload: Dict[str, Any] = {}

        # 监控类型（必填）
        if "monitor_type" in data or not partial:
            monitor_type = (data.get("monitor_type") or "").strip()
            if not monitor_type:
                raise ValueError("请选择监控类型")
            if monitor_type not in _VALID_MONITOR_TYPES:
                raise ValueError("监控类型不正确")
            payload["monitor_type"] = monitor_type

        # 所属分类（必填）
        if "category_id" in data or not partial:
            raw_category = data.get("category_id")
            if raw_category is None or raw_category == "":
                raise ValueError("请选择分类")
            try:
                category_id = int(raw_category)
            except (TypeError, ValueError):
                raise ValueError("分类参数不正确")
            # 校验分类存在且当前用户有权使用（普通用户仅限本人分类）
            await self._resolve_category(owner_id, category_id)
            payload["category_id"] = category_id

        # 关键字（必填）
        if "keyword" in data or not partial:
            keyword = (data.get("keyword") or "").strip()
            if not keyword:
                raise ValueError("商品关键字不能为空")
            if len(keyword) > 200:
                raise ValueError("商品关键字长度不能超过200个字符")
            payload["keyword"] = keyword

        # 价格区间
        price_min = _to_decimal(data["price_min"]) if "price_min" in data else None
        price_max = _to_decimal(data["price_max"]) if "price_max" in data else None
        if "price_min" in data:
            if price_min is not None and price_min < 0:
                raise ValueError("最低价格不能小于0")
            payload["price_min"] = price_min
        if "price_max" in data:
            if price_max is not None and price_max < 0:
                raise ValueError("最高价格不能小于0")
            payload["price_max"] = price_max
        if price_min is not None and price_max is not None and price_min > price_max:
            raise ValueError("最低价格不能大于最高价格")

        # 上新天数筛选（publishDays，可选；空/0=不限）
        if "publish_days" in data or not partial:
            raw_days = data.get("publish_days")
            if raw_days is None or raw_days == "" or raw_days == 0:
                payload["publish_days"] = None
            else:
                try:
                    publish_days = int(raw_days)
                except (TypeError, ValueError):
                    raise ValueError("上新天数必须为整数")
                if publish_days < 1 or publish_days > 365:
                    raise ValueError("上新天数必须为 1~365 之间的整数")
                payload["publish_days"] = publish_days

        # 降价监控不使用上新天数筛选（仅上新监控有效）
        if payload.get("monitor_type") == "price_drop" and "publish_days" in payload:
            payload["publish_days"] = None

        # 任务间隔
        if "interval_minutes" in data or not partial:
            raw_interval = data.get("interval_minutes")
            try:
                interval = int(raw_interval)
            except (TypeError, ValueError):
                raise ValueError("任务间隔必须为整数分钟")
            if interval < 1:
                raise ValueError("任务间隔必须大于等于1分钟")
            payload["interval_minutes"] = interval

        # 采集页数（必填，至少1页）
        if "collect_pages" in data or not partial:
            raw_pages = data.get("collect_pages")
            if raw_pages is None or raw_pages == "":
                raw_pages = 1
            try:
                collect_pages = int(raw_pages)
            except (TypeError, ValueError):
                raise ValueError("采集页数必须为整数")
            if collect_pages < 1:
                raise ValueError("采集页数必须大于等于1")
            payload["collect_pages"] = collect_pages

        # 代理API地址（可选；空=不使用代理）。调用该API返回代理IP列表，采集/详情时取一个作HTTP代理
        if "proxy_url" in data or not partial:
            proxy_url = (data.get("proxy_url") or "").strip()
            if proxy_url:
                if len(proxy_url) > 255:
                    raise ValueError("代理API地址长度不能超过255个字符")
                if not proxy_url.lower().startswith(("http://", "https://")):
                    raise ValueError("代理API地址格式不正确，需以 http:// 或 https:// 开头")
            payload["proxy_url"] = proxy_url or None

        # 采集账号列表（多选，非必填；不可用时回退用户级/管理员兜底采集账号）
        if "account_ids" in data or not partial:
            account_ids = await self._normalize_account_ids(owner_id, data.get("account_ids"))
            payload["account_ids"] = account_ids

        # 下单账号列表（多选，非必填；私信与下单共用，轮换使用）
        if "order_account_ids" in data or not partial:
            order_account_ids = await self._normalize_account_ids(owner_id, data.get("order_account_ids"))
            payload["order_account_ids"] = order_account_ids

        # 私信内容（配置下单账号后必填）
        if "dm_content" in data or not partial:
            dm_content = (data.get("dm_content") or "").strip()
            if len(dm_content) > 1000:
                raise ValueError("私信内容长度不能超过1000个字符")
            payload["dm_content"] = dm_content or None

        # 每次定时私信最多处理条数（默认5，1~100）
        if "dm_batch_size" in data or not partial:
            raw_batch = data.get("dm_batch_size")
            if raw_batch is None or raw_batch == "":
                raw_batch = 5
            try:
                dm_batch_size = int(raw_batch)
            except (TypeError, ValueError):
                raise ValueError("每次私信处理条数必须为整数")
            if dm_batch_size < 1:
                raise ValueError("每次私信处理条数必须大于等于1")
            if dm_batch_size > 100:
                raise ValueError("每次私信处理条数不能超过100")
            payload["dm_batch_size"] = dm_batch_size

        # 每次定时下单最多处理条数（默认5，1~100）
        if "order_batch_size" in data or not partial:
            raw_order_batch = data.get("order_batch_size")
            if raw_order_batch is None or raw_order_batch == "":
                raw_order_batch = 5
            try:
                order_batch_size = int(raw_order_batch)
            except (TypeError, ValueError):
                raise ValueError("每次下单处理条数必须为整数")
            if order_batch_size < 1:
                raise ValueError("每次下单处理条数必须大于等于1")
            if order_batch_size > 100:
                raise ValueError("每次下单处理条数不能超过100")
            payload["order_batch_size"] = order_batch_size

        # 采集后直接下单开关
        if "direct_order" in data or not partial:
            payload["direct_order"] = bool(data.get("direct_order"))

        # 创建时校验：配置了下单账号则私信内容必填（开启"采集后直接下单"时跳过私信，无需私信内容）
        if not partial and payload.get("order_account_ids") and not payload.get("dm_content") and not payload.get("direct_order"):
            raise ValueError("配置了下单账号后，私信内容必填（或开启采集后直接下单）")

        # 创建时校验：开启采集后直接下单需配置下单账号
        if not partial and payload.get("direct_order") and not payload.get("order_account_ids"):
            raise ValueError("开启采集后直接下单需配置下单账号")

        # 备注
        if "remark" in data:
            remark = (data.get("remark") or "").strip()
            payload["remark"] = remark or None

        return payload

    async def _normalize_account_ids(self, owner_id: Optional[int], raw_ids: Any) -> List[str]:
        """规整账号ID列表，并校验账号归属（普通用户只能选自己的账号）。"""
        if not raw_ids:
            return []
        if not isinstance(raw_ids, (list, tuple, set)):
            raise ValueError("账号列表格式不正确")

        cleaned: List[str] = []
        for item in raw_ids:
            account_id = str(item).strip()
            if account_id and account_id not in cleaned:
                cleaned.append(account_id)
        if not cleaned:
            return []

        # 校验账号是否存在且归属当前用户
        stmt = select(XYAccount.account_id).where(XYAccount.account_id.in_(cleaned))
        if owner_id is not None:
            stmt = stmt.where(XYAccount.owner_id == owner_id)
        valid_ids = {row for row in (await self.session.execute(stmt)).scalars().all()}
        invalid = [account_id for account_id in cleaned if account_id not in valid_ids]
        if invalid:
            raise ValueError(f"以下账号不存在或无权限使用：{', '.join(invalid)}")
        return cleaned

    def _scope_conditions(self, owner_id: Optional[int]) -> list:
        """构造数据隔离与软删除过滤条件。"""
        conditions = [ListingMonitorTask.is_deleted.is_(False)]
        if owner_id is not None:
            conditions.append(ListingMonitorTask.owner_id == owner_id)
        return conditions

    async def _batch_item_stats(self, task_ids: List[int]) -> Dict[int, Dict[str, int]]:
        """批量统计若干监控任务下采集商品的已私信、已下单（真实成功）、重复跳过数量。

        - ordered：仅统计真实下单成功（order_status='success'），不含因其他任务已下单而跳过的重复记录；
        - duplicate：因同用户其他监控任务已下单而跳过的重复记录数（order_status='duplicate'）。

        Returns: {task_id: {"dm_sent": int, "ordered": int, "duplicate": int}}
        """
        if not task_ids:
            return {}
        stmt = (
            select(
                ListingMonitorItem.monitor_task_id,
                func.sum(case((ListingMonitorItem.is_dm_sent.is_(True), 1), else_=0)).label("dm_sent"),
                func.sum(case((ListingMonitorItem.order_status == "success", 1), else_=0)).label("ordered"),
                func.sum(case((ListingMonitorItem.order_status == "duplicate", 1), else_=0)).label("duplicate"),
            )
            .where(ListingMonitorItem.monitor_task_id.in_(task_ids))
            .group_by(ListingMonitorItem.monitor_task_id)
        )
        result = (await self.session.execute(stmt)).all()
        return {
            row.monitor_task_id: {
                "dm_sent": int(row.dm_sent or 0),
                "ordered": int(row.ordered or 0),
                "duplicate": int(row.duplicate or 0),
            }
            for row in result
        }

    async def _batch_owner_names(self, owner_ids: Sequence[Optional[int]]) -> Dict[int, str]:
        """批量查询归属用户ID -> 用户名映射（用于列表展示所属用户）。"""
        ids = {oid for oid in owner_ids if oid is not None}
        if not ids:
            return {}
        stmt = select(User.id, User.username).where(User.id.in_(ids))
        return {row.id: row.username for row in (await self.session.execute(stmt)).all()}

    async def get_overview(self, owner_id: Optional[int]) -> Dict[str, Any]:
        """商品监控总览统计（按用户隔离；管理员 owner_id=None 统计全量）。

        采集/私信/下单数均按商品ID（item_id）去重，避免同商品被多任务重复计数。
        "今日"以北京时间当天 00:00:00 为界。

        Returns: 各项统计计数字典
        """
        today_start = get_beijing_now_naive().replace(hour=0, minute=0, second=0, microsecond=0)

        # ---- 任务维度 ----
        task_cond = [ListingMonitorTask.is_deleted.is_(False)]
        if owner_id is not None:
            task_cond.append(ListingMonitorTask.owner_id == owner_id)
        total_tasks = (
            await self.session.execute(
                select(func.count()).select_from(ListingMonitorTask).where(*task_cond)
            )
        ).scalar() or 0
        enabled_tasks = (
            await self.session.execute(
                select(func.count())
                .select_from(ListingMonitorTask)
                .where(*task_cond, ListingMonitorTask.is_enabled.is_(True))
            )
        ).scalar() or 0

        # ---- 今日任务执行日志维度 ----
        log_cond = [ListingMonitorLog.created_at >= today_start]
        if owner_id is not None:
            log_cond.append(ListingMonitorLog.owner_id == owner_id)
        log_status_rows = (
            await self.session.execute(
                select(ListingMonitorLog.status, func.count())
                .where(*log_cond)
                .group_by(ListingMonitorLog.status)
            )
        ).all()
        log_status_map = {status: int(cnt or 0) for status, cnt in log_status_rows}
        today_run_total = sum(log_status_map.values())
        today_run_success = log_status_map.get("success", 0)
        today_run_partial = log_status_map.get("partial", 0)
        today_run_failed = log_status_map.get("failed", 0)

        # ---- 采集商品维度（按 item_id 去重）----
        def _item_cond(extra=None):
            cond = []
            if owner_id is not None:
                cond.append(ListingMonitorItem.owner_id == owner_id)
            if extra is not None:
                cond.extend(extra)
            return cond

        distinct_item = func.count(func.distinct(ListingMonitorItem.item_id))

        # 累计采集商品数（去重）
        total_items = (
            await self.session.execute(
                select(distinct_item).where(*_item_cond())
            )
        ).scalar() or 0
        # 今日采集数（去重）：今日被采集到（last_seen_at），包含重复采集的商品
        today_collected = (
            await self.session.execute(
                select(distinct_item).where(*_item_cond([ListingMonitorItem.last_seen_at >= today_start]))
            )
        ).scalar() or 0
        # 今日新增商品数（去重）：今日首次入库（created_at），不包含重复采集
        today_new = (
            await self.session.execute(
                select(distinct_item).where(*_item_cond([ListingMonitorItem.created_at >= today_start]))
            )
        ).scalar() or 0
        # 今日私信成功数（去重）：今日实际发起私信（dm_sent_at 在成功/超时未确认时写入）
        today_dm = (
            await self.session.execute(
                select(distinct_item).where(*_item_cond([ListingMonitorItem.dm_sent_at >= today_start]))
            )
        ).scalar() or 0
        # 今日私信失败数（去重）：今日入库（created_at 在今日）且私信结果为失败（被拦截/账号不存在）
        today_dm_failed = (
            await self.session.execute(
                select(distinct_item).where(
                    *_item_cond([
                        ListingMonitorItem.created_at >= today_start,
                        ListingMonitorItem.dm_status == "failed",
                    ])
                )
            )
        ).scalar() or 0
        # 今日下单数（去重）：今日下单成功
        today_ordered = (
            await self.session.execute(
                select(distinct_item).where(*_item_cond([ListingMonitorItem.ordered_at >= today_start]))
            )
        ).scalar() or 0
        # 今日下单失败数（去重）：今日入库（created_at 在今日）且下单结果为失败
        today_order_failed = (
            await self.session.execute(
                select(distinct_item).where(
                    *_item_cond([
                        ListingMonitorItem.created_at >= today_start,
                        ListingMonitorItem.order_status == "failed",
                    ])
                )
            )
        ).scalar() or 0
        # 今日重复跳过数（去重）：今日入库（created_at 在今日）且下单结果为重复跳过
        today_order_duplicate = (
            await self.session.execute(
                select(distinct_item).where(
                    *_item_cond([
                        ListingMonitorItem.created_at >= today_start,
                        ListingMonitorItem.order_status == "duplicate",
                    ])
                )
            )
        ).scalar() or 0
        # 累计私信成功数（去重，按实际发起私信时间，排除直接下单跳过私信的商品）
        total_dm = (
            await self.session.execute(
                select(distinct_item).where(*_item_cond([ListingMonitorItem.dm_sent_at.isnot(None)]))
            )
        ).scalar() or 0
        # 累计下单成功数（去重，仅真实成功）
        total_ordered = (
            await self.session.execute(
                select(distinct_item).where(*_item_cond([ListingMonitorItem.order_status == "success"]))
            )
        ).scalar() or 0

        return {
            "total_tasks": int(total_tasks),
            "enabled_tasks": int(enabled_tasks),
            "disabled_tasks": int(total_tasks) - int(enabled_tasks),
            "today_run_total": today_run_total,
            "today_run_success": today_run_success,
            "today_run_partial": today_run_partial,
            "today_run_failed": today_run_failed,
            "today_collected": int(today_collected),
            "today_new": int(today_new),
            "today_dm": int(today_dm),
            "today_dm_failed": int(today_dm_failed),
            "today_ordered": int(today_ordered),
            "today_order_failed": int(today_order_failed),
            "today_order_duplicate": int(today_order_duplicate),
            "total_items": int(total_items),
            "total_dm": int(total_dm),
            "total_ordered": int(total_ordered),
        }

    async def list_tasks(
        self,
        owner_id: Optional[int],
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        category_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """分页查询上新监控任务列表。"""
        page = max(page, 1)
        page_size = page_size if page_size in _VALID_PAGE_SIZES else 20

        conditions = self._scope_conditions(owner_id)
        if keyword:
            conditions.append(ListingMonitorTask.keyword.like(f"%{keyword.strip()}%"))
        if is_enabled is not None:
            conditions.append(ListingMonitorTask.is_enabled.is_(is_enabled))
        # 按分类筛选（category_id 为 None 时不限制）
        if category_id is not None:
            conditions.append(ListingMonitorTask.category_id == category_id)

        count_stmt = select(func.count()).select_from(ListingMonitorTask).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(ListingMonitorTask)
            .where(*conditions)
            .order_by(desc(ListingMonitorTask.updated_at), desc(ListingMonitorTask.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        # 统计每个任务下采集商品的已私信、已下单数量
        stats_map = await self._batch_item_stats([row.id for row in rows])
        # 批量查归属用户名（用于管理员视角展示所属用户）
        owner_name_map = await self._batch_owner_names([row.owner_id for row in rows])
        task_list = []
        for row in rows:
            task_dict = _task_to_dict(row)
            stat = stats_map.get(row.id, {})
            task_dict["dm_sent_count"] = stat.get("dm_sent", 0)
            task_dict["ordered_count"] = stat.get("ordered", 0)
            task_dict["duplicate_count"] = stat.get("duplicate", 0)
            task_dict["owner_username"] = owner_name_map.get(row.owner_id)
            task_list.append(task_dict)

        return {
            "list": task_list,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }

    async def get(self, owner_id: Optional[int], task_id: int) -> ListingMonitorTask | None:
        """按主键查询监控任务（带数据隔离与软删除过滤）。"""
        conditions = self._scope_conditions(owner_id)
        conditions.append(ListingMonitorTask.id == task_id)
        stmt = select(ListingMonitorTask).where(*conditions)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(self, owner_id: Optional[int], operator_user_id: int, data: dict) -> ListingMonitorTask:
        """创建上新监控任务。"""
        payload = await self._normalize_payload(owner_id, data, partial=False)
        task = ListingMonitorTask(
            owner_id=owner_id if owner_id is not None else operator_user_id,
            created_by=operator_user_id,
            is_enabled=bool(data.get("is_enabled", True)),
            **payload,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def update(self, owner_id: Optional[int], task_id: int, data: dict) -> ListingMonitorTask | None:
        """更新上新监控任务。"""
        task = await self.get(owner_id, task_id)
        if not task:
            return None

        payload = await self._normalize_payload(owner_id, data, partial=True)

        # 部分更新时用“新值优先、否则沿用库中旧值”的有效值，校验价格区间，避免绕过交叉校验
        effective_min = payload.get("price_min", task.price_min) if "price_min" in payload else task.price_min
        effective_max = payload.get("price_max", task.price_max) if "price_max" in payload else task.price_max
        if effective_min is not None and effective_max is not None and Decimal(str(effective_min)) > Decimal(str(effective_max)):
            raise ValueError("最低价格不能大于最高价格")

        # 私信内容必填校验：用"新值优先、否则沿用库中旧值"的有效值（开启直接下单则跳过私信，无需私信内容）
        effective_order_accounts = payload.get("order_account_ids") if "order_account_ids" in payload else task.order_account_ids
        effective_dm_content = payload.get("dm_content") if "dm_content" in payload else task.dm_content
        effective_direct_order = payload.get("direct_order") if "direct_order" in payload else task.direct_order
        if effective_order_accounts and not effective_dm_content and not effective_direct_order:
            raise ValueError("配置了下单账号后，私信内容必填（或开启采集后直接下单）")
        if effective_direct_order and not effective_order_accounts:
            raise ValueError("开启采集后直接下单需配置下单账号")

        for field_name, field_value in payload.items():
            setattr(task, field_name, field_value)
        if "is_enabled" in data:
            task.is_enabled = bool(data["is_enabled"])

        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def update_status(self, owner_id: Optional[int], task_id: int, is_enabled: bool) -> ListingMonitorTask | None:
        """启用/停用监控任务。"""
        task = await self.get(owner_id, task_id)
        if not task:
            return None
        task.is_enabled = bool(is_enabled)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def batch_delete(self, owner_id: Optional[int], task_ids: Sequence[int]) -> int:
        """批量软删除监控任务。"""
        normalized_ids: List[int] = []
        for raw_id in task_ids:
            try:
                task_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if task_id > 0 and task_id not in normalized_ids:
                normalized_ids.append(task_id)

        if not normalized_ids:
            raise ValueError("请选择要删除的监控任务")

        conditions = self._scope_conditions(owner_id)
        conditions.append(ListingMonitorTask.id.in_(normalized_ids))
        stmt = select(ListingMonitorTask).where(*conditions)
        tasks = (await self.session.execute(stmt)).scalars().all()
        now = get_beijing_now_naive()
        for task in tasks:
            task.is_deleted = True
            task.updated_at = now

        await self.session.commit()
        return len(tasks)

    async def batch_update_accounts(
        self,
        owner_id: Optional[int],
        task_ids: Sequence[int],
        field: str,
        account_ids: Any,
    ) -> int:
        """批量修改监控任务的账号字段（采集账号 account_ids 或下单账号 order_account_ids）。

        Args:
            field: 仅允许 "account_ids"（采集账号）或 "order_account_ids"（下单账号）
            account_ids: 选择的账号ID列表（会校验归属，普通用户只能选自己的账号）；
                传空数组表示清空该字段配置（采集账号清空→回退用户/管理员兜底；
                下单账号清空→该任务不再下单）。

        Returns: 实际更新的任务数
        """
        if field not in ("account_ids", "order_account_ids"):
            raise ValueError("不支持的批量修改字段")

        normalized_ids: List[int] = []
        for raw_id in task_ids:
            try:
                task_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if task_id > 0 and task_id not in normalized_ids:
                normalized_ids.append(task_id)
        if not normalized_ids:
            raise ValueError("请选择要修改的监控任务")

        # 允许传空数组清空该字段；非空时按归属校验
        valid_account_ids = await self._normalize_account_ids(owner_id, account_ids)

        conditions = self._scope_conditions(owner_id)
        conditions.append(ListingMonitorTask.id.in_(normalized_ids))
        stmt = select(ListingMonitorTask).where(*conditions)
        tasks = (await self.session.execute(stmt)).scalars().all()
        now = get_beijing_now_naive()
        for task in tasks:
            setattr(task, field, valid_account_ids)
            task.updated_at = now

        await self.session.commit()
        return len(tasks)

    async def batch_update_category(
        self,
        owner_id: Optional[int],
        task_ids: Sequence[int],
        category_id: Any,
    ) -> int:
        """批量修改监控任务的所属分类（分类必填、须存在且当前用户有权使用）。

        Returns: 实际更新的任务数
        """
        if category_id is None or category_id == "":
            raise ValueError("请选择分类")
        try:
            category_id = int(category_id)
        except (TypeError, ValueError):
            raise ValueError("分类参数不正确")
        # 校验分类存在且当前用户有权使用（普通用户仅限本人分类）
        await self._resolve_category(owner_id, category_id)

        normalized_ids: List[int] = []
        for raw_id in task_ids:
            try:
                tid = int(raw_id)
            except (TypeError, ValueError):
                continue
            if tid > 0 and tid not in normalized_ids:
                normalized_ids.append(tid)
        if not normalized_ids:
            raise ValueError("请选择要修改的监控任务")

        conditions = self._scope_conditions(owner_id)
        conditions.append(ListingMonitorTask.id.in_(normalized_ids))
        stmt = select(ListingMonitorTask).where(*conditions)
        tasks = (await self.session.execute(stmt)).scalars().all()
        now = get_beijing_now_naive()
        for task in tasks:
            task.category_id = category_id
            task.updated_at = now

        await self.session.commit()
        return len(tasks)

    async def batch_update_dm_content(
        self,
        owner_id: Optional[int],
        task_ids: Sequence[int],
        dm_content: Any,
    ) -> int:
        """批量修改监控任务的私信内容（非空、≤1000字）。

        说明：批量场景仅支持设置统一的私信内容，不支持批量清空（清空请逐条编辑），
        避免误操作把多条任务的私信内容一次性清掉。

        Returns: 实际更新的任务数
        """
        content = (str(dm_content).strip() if dm_content is not None else "")
        if not content:
            raise ValueError("请输入私信内容")
        if len(content) > 1000:
            raise ValueError("私信内容长度不能超过1000个字符")

        normalized_ids: List[int] = []
        for raw_id in task_ids:
            try:
                tid = int(raw_id)
            except (TypeError, ValueError):
                continue
            if tid > 0 and tid not in normalized_ids:
                normalized_ids.append(tid)
        if not normalized_ids:
            raise ValueError("请选择要修改的监控任务")

        conditions = self._scope_conditions(owner_id)
        conditions.append(ListingMonitorTask.id.in_(normalized_ids))
        stmt = select(ListingMonitorTask).where(*conditions)
        tasks = (await self.session.execute(stmt)).scalars().all()
        now = get_beijing_now_naive()
        for task in tasks:
            task.dm_content = content
            task.updated_at = now

        await self.session.commit()
        return len(tasks)

    async def reset_items_dm_failed(
        self,
        owner_id: Optional[int],
        item_ids: Sequence[int],
    ) -> int:
        """将选中的"私信失败"采集商品重置为"未私信"状态，等待定时任务重试。

        仅处理 dm_status='failed' 的采集商品（含前端展示的"重试中"与"已放弃"两种）：
        - 清空私信结果字段（dm_status / dm_fail_reason / dm_account_id）；
        - 重置私信尝试次数 dm_attempts=0，使其重新满足"采集商品发送私信"定时任务
          的处理条件（dm_attempts < 上限），等待下次定时任务自动重试；
        - 保持 is_dm_sent=False（确实未私信）。
        非"私信失败"状态的商品（未私信/等待重试/已发待确认/私信成功）一律跳过，不受影响。

        Args:
            owner_id: 归属用户ID（普通用户仅能操作本人数据，管理员为 None 不限）
            item_ids: 选中的采集商品主键ID列表

        Returns: 实际重置的采集商品数
        """
        normalized_ids: List[int] = []
        for raw_id in item_ids:
            try:
                pk = int(raw_id)
            except (TypeError, ValueError):
                continue
            if pk > 0 and pk not in normalized_ids:
                normalized_ids.append(pk)
        if not normalized_ids:
            raise ValueError("请选择要重置的采集商品")

        conditions = [ListingMonitorItem.id.in_(normalized_ids)]
        # 多用户数据隔离：普通用户仅能操作本人采集商品（与 list_items 一致）
        if owner_id is not None:
            conditions.append(ListingMonitorItem.owner_id == owner_id)
        # 仅重置"私信失败"的数据，避免误重置正常/成功的商品
        conditions.append(ListingMonitorItem.dm_status == "failed")

        stmt = select(ListingMonitorItem).where(*conditions)
        items = (await self.session.execute(stmt)).scalars().all()
        now = get_beijing_now_naive()
        for item in items:
            item.is_dm_sent = False
            item.dm_status = None
            item.dm_fail_reason = None
            item.dm_account_id = None
            item.dm_attempts = 0
            item.updated_at = now

        await self.session.commit()
        return len(items)

    async def collect_log_account_cookies(
        self,
        owner_id: Optional[int],
        log_ids: Sequence[int],
    ) -> List[Dict[str, Any]]:
        """根据监控日志ID集合，汇总去重后的账号信息（账号ID、Cookie、分销秘钥），用于复制。

        - 账号来源：每条日志关联的监控任务(monitor_task_id) 所配置的账号列表(account_ids)；
          即"根据日志找到监控任务，再取任务里配置的采集账号"，而非日志实际执行时用到的账号
          （失败的执行可能没有记录实际账号）。
        - 多条日志可能关联同一任务，按 account_id 去重（保留首次出现顺序）；
        - 分销秘钥：取该账号所属用户(owner)的 secret_key（个人设置-分销模块），一个账号一条。

        Returns: [{"account_id": str, "cookies": str, "secret_key": str}, ...]
        """
        normalized_ids: List[int] = []
        for raw_id in log_ids:
            try:
                log_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if log_id > 0 and log_id not in normalized_ids:
                normalized_ids.append(log_id)
        if not normalized_ids:
            raise ValueError("请选择要复制的监控日志")

        # 1) 由日志找到其关联的监控任务ID（按日志ID顺序保留任务首次出现顺序）
        log_conditions = [ListingMonitorLog.id.in_(normalized_ids)]
        if owner_id is not None:
            log_conditions.append(ListingMonitorLog.owner_id == owner_id)
        log_rows = (
            await self.session.execute(
                select(ListingMonitorLog.id, ListingMonitorLog.monitor_task_id)
                .where(*log_conditions)
                .order_by(ListingMonitorLog.id.desc())
            )
        ).all()

        ordered_task_ids: List[int] = []
        seen_task: set[int] = set()
        for _log_id, task_id in log_rows:
            if task_id and task_id not in seen_task:
                seen_task.add(task_id)
                ordered_task_ids.append(task_id)
        if not ordered_task_ids:
            return []

        # 2) 取这些监控任务配置的账号ID列表(account_ids)，去重保序
        task_conditions = [ListingMonitorTask.id.in_(ordered_task_ids)]
        if owner_id is not None:
            task_conditions.append(ListingMonitorTask.owner_id == owner_id)
        task_rows = (
            await self.session.execute(
                select(ListingMonitorTask.id, ListingMonitorTask.account_ids).where(*task_conditions)
            )
        ).all()
        task_account_map = {tid: (acc_ids or []) for tid, acc_ids in task_rows}

        ordered_account_ids: List[str] = []
        seen: set[str] = set()
        for task_id in ordered_task_ids:
            for aid in list(task_account_map.get(task_id) or []):
                if not aid:
                    continue
                aid = str(aid)
                if aid not in seen:
                    seen.add(aid)
                    ordered_account_ids.append(aid)
        if not ordered_account_ids:
            return []

        # 查询账号 Cookie（普通用户仅限本人账号，管理员不限）
        acc_conditions = [XYAccount.account_id.in_(ordered_account_ids)]
        if owner_id is not None:
            acc_conditions.append(XYAccount.owner_id == owner_id)
        acc_rows = list(
            (await self.session.execute(select(XYAccount).where(*acc_conditions))).scalars().all()
        )
        acc_map = {acc.account_id: acc for acc in acc_rows}

        # 查询各账号所属用户的分销秘钥
        owner_ids = {acc.owner_id for acc in acc_rows if acc.owner_id is not None}
        secret_map: Dict[int, Optional[str]] = {}
        if owner_ids:
            for uid, secret_key in (
                await self.session.execute(
                    select(User.id, User.secret_key).where(User.id.in_(owner_ids))
                )
            ).all():
                secret_map[uid] = secret_key

        result: List[Dict[str, Any]] = []
        for aid in ordered_account_ids:
            acc = acc_map.get(aid)
            if not acc:
                continue
            result.append(
                {
                    "account_id": acc.account_id,
                    "cookies": acc.cookie or "",
                    "secret_key": secret_map.get(acc.owner_id) or "",
                }
            )
        return result

    async def list_task_options(self, owner_id: Optional[int]) -> List[Dict[str, Any]]:
        """查询监控任务下拉选项（用于日志/采集商品页按任务筛选）。"""
        conditions = self._scope_conditions(owner_id)
        stmt = (
            select(ListingMonitorTask.id, ListingMonitorTask.keyword, ListingMonitorTask.monitor_type)
            .where(*conditions)
            .order_by(desc(ListingMonitorTask.id))
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"id": row.id, "keyword": row.keyword, "monitor_type": row.monitor_type} for row in rows]

    async def list_logs(
        self,
        owner_id: Optional[int],
        page: int = 1,
        page_size: int = 20,
        monitor_task_id: Optional[int] = None,
        status: Optional[str] = None,
        monitor_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页查询监控执行日志。"""
        page = max(page, 1)
        page_size = page_size if page_size in _VALID_PAGE_SIZES else 20

        conditions = []
        if owner_id is not None:
            conditions.append(ListingMonitorLog.owner_id == owner_id)
        if monitor_task_id:
            conditions.append(ListingMonitorLog.monitor_task_id == monitor_task_id)
        if status:
            conditions.append(ListingMonitorLog.status == status.strip())
        if monitor_type:
            conditions.append(ListingMonitorLog.monitor_type == monitor_type.strip())

        count_stmt = select(func.count()).select_from(ListingMonitorLog).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(ListingMonitorLog)
            .where(*conditions)
            .order_by(desc(ListingMonitorLog.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        return {
            "list": [_log_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }

    async def clear_logs(self, owner_id: Optional[int]) -> Dict[str, Any]:
        """清空监控日志：仅删除 LOG_RETENTION_DAYS 天之前的记录（日志表直接物理删除）。

        Args:
            owner_id: 数据隔离范围；普通用户仅清理本人日志，管理员（None）清理全部。

        Returns:
            {"deleted_count": 删除条数}
        """
        cutoff_time = get_beijing_now_naive() - timedelta(days=LOG_RETENTION_DAYS)
        conditions = [ListingMonitorLog.created_at < cutoff_time]
        if owner_id is not None:
            conditions.append(ListingMonitorLog.owner_id == owner_id)

        stmt = delete(ListingMonitorLog).where(*conditions)
        result = await self.session.execute(stmt)
        await self.session.commit()

        deleted_count = result.rowcount or 0
        logger.info(
            f"[商品监控日志] 已清空 {deleted_count} 条 {LOG_RETENTION_DAYS} 天前的监控日志"
            f"（owner_id={owner_id}，清理时间界限: {cutoff_time}）"
        )
        return {"deleted_count": deleted_count}

    async def list_items(
        self,
        owner_id: Optional[int],
        page: int = 1,
        page_size: int = 20,
        monitor_task_id: Optional[int] = None,
        keyword: Optional[str] = None,
        area: Optional[str] = None,
        seller_nick: Optional[str] = None,
        item_id: Optional[str] = None,
        is_dm_sent: Optional[bool] = None,
        is_ordered: Optional[bool] = None,
        seller_fill: Optional[str] = None,
        has_detail: Optional[bool] = None,
        dm_state: Optional[str] = None,
        order_state: Optional[str] = None,
        created_start: Optional[str] = None,
        created_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页查询采集商品信息。"""
        page = max(page, 1)
        page_size = page_size if page_size in _VALID_PAGE_SIZES else 20

        conditions = []
        if owner_id is not None:
            conditions.append(ListingMonitorItem.owner_id == owner_id)
        if monitor_task_id:
            conditions.append(ListingMonitorItem.monitor_task_id == monitor_task_id)
        if keyword:
            conditions.append(ListingMonitorItem.title.like(f"%{keyword.strip()}%"))
        if area:
            conditions.append(ListingMonitorItem.area.like(f"%{area.strip()}%"))
        if seller_nick:
            conditions.append(ListingMonitorItem.seller_nick.like(f"%{seller_nick.strip()}%"))
        if item_id:
            conditions.append(ListingMonitorItem.item_id == item_id.strip())
        # 私信状态（优先使用 dm_state 多状态筛选；未传时回退旧的 is_dm_sent 布尔筛选）
        # 状态语义与列表展示保持一致：
        #   not_sent-未私信 / waiting-等待重试 / pending-已发待确认 / success-私信成功 / failed-私信失败
        if dm_state == "not_sent":
            conditions.append(ListingMonitorItem.is_dm_sent.is_(False))
            conditions.append(
                or_(
                    ListingMonitorItem.dm_status.is_(None),
                    ListingMonitorItem.dm_status.notin_(["failed", "waiting"]),
                )
            )
        elif dm_state == "waiting":
            # 等待重试：下单账号暂时不可用，已记录原因、未私信、下轮继续重试
            conditions.append(ListingMonitorItem.is_dm_sent.is_(False))
            conditions.append(ListingMonitorItem.dm_status == "waiting")
        elif dm_state == "success":
            conditions.append(ListingMonitorItem.dm_status == "success")
        elif dm_state == "failed":
            conditions.append(ListingMonitorItem.dm_status == "failed")
        elif dm_state == "pending":
            conditions.append(ListingMonitorItem.is_dm_sent.is_(True))
            conditions.append(
                or_(
                    ListingMonitorItem.dm_status.is_(None),
                    ListingMonitorItem.dm_status.notin_(["success", "failed"]),
                )
            )
        elif is_dm_sent is not None:
            conditions.append(ListingMonitorItem.is_dm_sent.is_(is_dm_sent))
        # 下单状态（优先使用 order_state 多状态筛选；未传时回退旧的 is_ordered 布尔筛选）
        # 状态语义与列表展示保持一致：
        #   not_ordered-未下单 / ordered-已下单 / failed-下单失败 / no_account-无可用账号 / duplicate-重复跳过
        if order_state == "ordered":
            conditions.append(ListingMonitorItem.is_ordered.is_(True))
            # 排除"重复跳过"：其同样标记 is_ordered=True，但展示为"重复跳过"而非"已下单"，
            # 故"已下单"筛选需排除 duplicate，与列表徽标语义保持一致
            conditions.append(
                or_(
                    ListingMonitorItem.order_status.is_(None),
                    ListingMonitorItem.order_status != "duplicate",
                )
            )
        elif order_state == "duplicate":
            conditions.append(ListingMonitorItem.order_status == "duplicate")
        elif order_state == "no_account":
            conditions.append(ListingMonitorItem.is_ordered.is_(False))
            conditions.append(ListingMonitorItem.order_status == "no_account")
        elif order_state == "failed":
            conditions.append(ListingMonitorItem.is_ordered.is_(False))
            conditions.append(ListingMonitorItem.order_status == "failed")
        elif order_state == "not_ordered":
            conditions.append(ListingMonitorItem.is_ordered.is_(False))
            conditions.append(
                or_(
                    ListingMonitorItem.order_status.is_(None),
                    ListingMonitorItem.order_status.notin_(["duplicate", "no_account", "failed"]),
                )
            )
        elif is_ordered is not None:
            conditions.append(ListingMonitorItem.is_ordered.is_(is_ordered))
        # 采集时间区间（created_at，北京时间）
        created_start_dt = _parse_naive_datetime(created_start)
        if created_start_dt is not None:
            conditions.append(ListingMonitorItem.created_at >= created_start_dt)
        created_end_dt = _parse_naive_datetime(created_end)
        if created_end_dt is not None:
            conditions.append(ListingMonitorItem.created_at <= created_end_dt)
        if has_detail is not None:
            if has_detail:
                conditions.append(ListingMonitorItem.detail_json.isnot(None))
            else:
                conditions.append(ListingMonitorItem.detail_json.is_(None))
        # 卖家补全状态：filled-已补全 / pending-待补全 / failed-补全失败
        if seller_fill == "filled":
            conditions.append(ListingMonitorItem.seller_user_id.isnot(None))
            conditions.append(ListingMonitorItem.seller_user_id != "")
        elif seller_fill == "failed":
            conditions.append(ListingMonitorItem.seller_fill_status == "failed")
        elif seller_fill == "pending":
            conditions.append(
                or_(
                    ListingMonitorItem.seller_user_id.is_(None),
                    ListingMonitorItem.seller_user_id == "",
                )
            )
            conditions.append(
                or_(
                    ListingMonitorItem.seller_fill_status.is_(None),
                    ListingMonitorItem.seller_fill_status != "failed",
                )
            )

        count_stmt = select(func.count()).select_from(ListingMonitorItem).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(ListingMonitorItem)
            .where(*conditions)
            .order_by(desc(ListingMonitorItem.publish_time), desc(ListingMonitorItem.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        # 批量查询本页商品所属监控任务的关键字（任务名称），用于前端展示
        task_keyword_map: Dict[int, str] = {}
        task_ids = {row.monitor_task_id for row in rows if row.monitor_task_id is not None}
        if task_ids:
            kw_stmt = select(ListingMonitorTask.id, ListingMonitorTask.keyword).where(
                ListingMonitorTask.id.in_(task_ids)
            )
            for tid, kw in (await self.session.execute(kw_stmt)).all():
                task_keyword_map[tid] = kw

        return {
            "list": [
                _item_to_dict(row, task_keyword_map.get(row.monitor_task_id)) for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }

    async def get_item(self, owner_id: Optional[int], item_pk: int) -> Optional[Dict[str, Any]]:
        """查询单条采集商品的完整信息（含详情/原始JSON），用于详情弹窗展示。"""
        conditions = [ListingMonitorItem.id == item_pk]
        if owner_id is not None:
            conditions.append(ListingMonitorItem.owner_id == owner_id)
        stmt = select(ListingMonitorItem).where(*conditions)
        item = (await self.session.execute(stmt)).scalar_one_or_none()
        if not item:
            return None
        # 查询所属监控任务关键字（任务名称）
        task_keyword = None
        if item.monitor_task_id is not None:
            task_keyword = (
                await self.session.execute(
                    select(ListingMonitorTask.keyword).where(
                        ListingMonitorTask.id == item.monitor_task_id
                    )
                )
            ).scalar_one_or_none()
        data = _item_to_dict(item, task_keyword)
        # 附带数据库中存储的原始详情与搜索原始数据（解析为对象，便于前端展示）
        data["detail_json"] = _safe_json_loads(item.detail_json)
        data["raw_json"] = _safe_json_loads(item.raw_json)
        return data


__all__ = ["ListingMonitorService", "_task_to_dict"]
