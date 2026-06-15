"""
公共商品上新监控任务服务

功能：
1. 提供上新监控任务的分页查询与维护能力
2. 处理多用户数据隔离（owner_id）与软删除（is_deleted）
3. 校验关键字、价格区间、任务间隔、账号列表等业务规则
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.listing_monitor_task import ListingMonitorTask
from common.models.listing_monitor_item import ListingMonitorItem
from common.models.listing_monitor_log import ListingMonitorLog
from common.models.xy_account import XYAccount
from common.utils.time_utils import get_beijing_now_naive, safe_isoformat

# 合法分页大小
_VALID_PAGE_SIZES = (10, 20, 50, 100)

# 合法监控类型：listing-上新监控，price_drop-降价监控
_VALID_MONITOR_TYPES = ("listing", "price_drop")


def _to_decimal(value: Any) -> Optional[Decimal]:
    """将输入安全转换为两位小数的 Decimal，空值返回 None。"""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("价格格式不正确")


def _task_to_dict(task: ListingMonitorTask) -> Dict[str, Any]:
    """将监控任务模型转换为前端可用的字典。"""
    return {
        "id": task.id,
        "monitor_type": task.monitor_type,
        "keyword": task.keyword,
        "price_min": float(task.price_min) if task.price_min is not None else None,
        "price_max": float(task.price_max) if task.price_max is not None else None,
        "interval_minutes": task.interval_minutes,
        "collect_pages": task.collect_pages,
        "account_ids": list(task.account_ids or []),
        "dm_account_id": task.dm_account_id,
        "dm_content": task.dm_content,
        "order_account_id": task.order_account_id,
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


def _item_to_dict(item: ListingMonitorItem) -> Dict[str, Any]:
    """将采集商品模型转换为前端可用的字典。"""
    return {
        "id": item.id,
        "monitor_task_id": item.monitor_task_id,
        "item_id": item.item_id,
        "title": item.title,
        "price": item.price,
        "area": item.area,
        "pic_url": item.pic_url,
        "seller_id": item.seller_id,
        "seller_user_id": item.seller_user_id,
        "seller_nick": item.seller_nick,
        "want_count": item.want_count,
        "publish_time": safe_isoformat(item.publish_time),
        "target_url": item.target_url,
        "has_detail": bool(item.detail_json),
        "is_dm_sent": bool(item.is_dm_sent),
        "is_ordered": bool(item.is_ordered),
        "last_seen_at": safe_isoformat(item.last_seen_at),
        "created_at": safe_isoformat(item.created_at),
        "updated_at": safe_isoformat(item.updated_at),
    }


class ListingMonitorService:
    """商品上新监控任务服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session

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

        # 账号列表（多选，必填：至少关联一个账号）
        if "account_ids" in data or not partial:
            account_ids = await self._normalize_account_ids(owner_id, data.get("account_ids"))
            if not account_ids:
                raise ValueError("请至少选择一个关联账号")
            payload["account_ids"] = account_ids

        # 私信账号（单选，非必填）
        if "dm_account_id" in data or not partial:
            payload["dm_account_id"] = await self._validate_single_account(
                owner_id, data.get("dm_account_id"), "私信账号"
            )

        # 私信内容（填写私信账号后必填）
        if "dm_content" in data or not partial:
            dm_content = (data.get("dm_content") or "").strip()
            if len(dm_content) > 1000:
                raise ValueError("私信内容长度不能超过1000个字符")
            payload["dm_content"] = dm_content or None

        # 下单账号（单选，非必填）
        if "order_account_id" in data or not partial:
            payload["order_account_id"] = await self._validate_single_account(
                owner_id, data.get("order_account_id"), "下单账号"
            )

        # 创建时校验：填写了私信账号则私信内容必填（更新走 update() 的有效值校验）
        if not partial and payload.get("dm_account_id") and not payload.get("dm_content"):
            raise ValueError("填写了私信账号后，私信内容必填")

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

    async def _validate_single_account(
        self, owner_id: Optional[int], account_id: Any, label: str
    ) -> Optional[str]:
        """校验单个账号ID（非必填）：空返回 None，非空则校验存在且归属当前用户。"""
        if account_id is None:
            return None
        aid = str(account_id).strip()
        if not aid:
            return None
        stmt = select(XYAccount.account_id).where(XYAccount.account_id == aid)
        if owner_id is not None:
            stmt = stmt.where(XYAccount.owner_id == owner_id)
        exists = (await self.session.execute(stmt)).scalar_one_or_none()
        if not exists:
            raise ValueError(f"{label}不存在或无权限使用")
        return aid

    def _scope_conditions(self, owner_id: Optional[int]) -> list:
        """构造数据隔离与软删除过滤条件。"""
        conditions = [ListingMonitorTask.is_deleted.is_(False)]
        if owner_id is not None:
            conditions.append(ListingMonitorTask.owner_id == owner_id)
        return conditions

    async def list_tasks(
        self,
        owner_id: Optional[int],
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        is_enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """分页查询上新监控任务列表。"""
        page = max(page, 1)
        page_size = page_size if page_size in _VALID_PAGE_SIZES else 20

        conditions = self._scope_conditions(owner_id)
        if keyword:
            conditions.append(ListingMonitorTask.keyword.like(f"%{keyword.strip()}%"))
        if is_enabled is not None:
            conditions.append(ListingMonitorTask.is_enabled.is_(is_enabled))

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

        return {
            "list": [_task_to_dict(row) for row in rows],
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

        # 私信内容必填校验：用"新值优先、否则沿用库中旧值"的有效值
        effective_dm_account = payload.get("dm_account_id") if "dm_account_id" in payload else task.dm_account_id
        effective_dm_content = payload.get("dm_content") if "dm_content" in payload else task.dm_content
        if effective_dm_account and not effective_dm_content:
            raise ValueError("填写了私信账号后，私信内容必填")

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

    async def list_items(
        self,
        owner_id: Optional[int],
        page: int = 1,
        page_size: int = 20,
        monitor_task_id: Optional[int] = None,
        keyword: Optional[str] = None,
        area: Optional[str] = None,
        seller_nick: Optional[str] = None,
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

        return {
            "list": [_item_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }


__all__ = ["ListingMonitorService", "_task_to_dict"]
