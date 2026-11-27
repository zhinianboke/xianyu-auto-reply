"""采集商品分页和详情查询，列表只读取本页的展示数据。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import LargeBinary, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from common.db.retry import with_db_retry
from common.models.listing_monitor_item import ListingMonitorItem
from common.models.listing_monitor_task import ListingMonitorTask
from common.utils.pagination import build_pagination_response
from common.utils.time_utils import safe_isoformat

LISTING_MONITOR_PAGE_SIZES = (10, 20, 50, 100)


def _parse_naive_datetime(value: str | None) -> datetime | None:
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


def _safe_json_loads(text: str | None) -> Any:
    """安全解析 JSON 字符串，失败或空返回 None。"""
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _item_to_dict(item: ListingMonitorItem, task_keyword: str | None, *, has_detail: bool) -> dict[str, Any]:
    """将采集商品模型转换为前端可用的字典。

    参数为商品、任务关键字和详情标记，返回列表及详情共用的字段。
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
        "is_free_shipping": item.is_free_shipping,
        "seller_credit_level": item.seller_credit_level,
        "seller_credit_label": item.seller_credit_label,
        "publish_time": safe_isoformat(item.publish_time),
        "target_url": item.target_url,
        "has_detail": has_detail,
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


def _item_page_statement(conditions: list, offset: int, limit: int):
    """用相同筛选先分页取主键，再读取本页字段和任务关键字。"""
    item = ListingMonitorItem
    order_by = (item.publish_time.desc(), item.id.desc())
    page_ids = (
        select(item.id)
        .where(*conditions)
        .order_by(*order_by)
        .offset(offset)
        .limit(limit)
        .subquery("page_items")
    )
    return (
        select(item, ListingMonitorTask.keyword, func.length(cast(item.detail_json, LargeBinary)) > 0)
        .options(defer(item.raw_json, raiseload=True), defer(item.detail_json, raiseload=True))
        .join(page_ids, page_ids.c.id == item.id)
        .outerjoin(ListingMonitorTask, ListingMonitorTask.id == item.monitor_task_id)
        .order_by(*order_by)
    )


class ListingMonitorItemQueryService:
    """采集商品列表及详情，沿用调用方解析的用户权限。"""

    def __init__(self, session: AsyncSession):
        """保存当前请求的数据库会话。"""
        self.session = session

    @with_db_retry(max_retries=2)
    async def list_items(
        self,
        owner_id: int | None,
        page: int = 1,
        page_size: int = 20,
        monitor_task_id: int | None = None,
        keyword: str | None = None,
        area: str | None = None,
        seller_nick: str | None = None,
        item_id: str | None = None,
        is_dm_sent: bool | None = None,
        is_ordered: bool | None = None,
        seller_fill: str | None = None,
        has_detail: bool | None = None,
        dm_state: str | None = None,
        order_state: str | None = None,
        created_start: str | None = None,
        created_end: str | None = None,
    ) -> dict[str, Any]:
        """分页查询采集商品信息。"""
        page = max(page, 1)
        page_size = page_size if page_size in LISTING_MONITOR_PAGE_SIZES else 20

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
            conditions.append(ListingMonitorItem.is_dm_sent == 0)
            conditions.append(
                or_(
                    ListingMonitorItem.dm_status.is_(None),
                    ListingMonitorItem.dm_status.notin_(["failed", "waiting"]),
                )
            )
        elif dm_state == "waiting":
            # 等待重试：下单账号暂时不可用，已记录原因、未私信、下轮继续重试
            conditions.append(ListingMonitorItem.is_dm_sent == 0)
            conditions.append(ListingMonitorItem.dm_status == "waiting")
        elif dm_state == "success":
            conditions.append(ListingMonitorItem.dm_status == "success")
        elif dm_state == "failed":
            conditions.append(ListingMonitorItem.dm_status == "failed")
        elif dm_state == "pending":
            conditions.append(ListingMonitorItem.is_dm_sent == 1)
            conditions.append(
                or_(
                    ListingMonitorItem.dm_status.is_(None),
                    ListingMonitorItem.dm_status.notin_(["success", "failed"]),
                )
            )
        elif is_dm_sent is not None:
            conditions.append(ListingMonitorItem.is_dm_sent == int(is_dm_sent))
        # 下单状态（优先使用 order_state 多状态筛选；未传时回退旧的 is_ordered 布尔筛选）
        # 状态语义与列表展示保持一致：
        #   not_ordered-未下单 / ordered-已下单 / failed-下单失败 / no_account-无可用账号 / duplicate-重复跳过
        if order_state == "ordered":
            conditions.append(ListingMonitorItem.is_ordered == 1)
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
            conditions.append(ListingMonitorItem.is_ordered == 0)
            conditions.append(ListingMonitorItem.order_status == "no_account")
        elif order_state == "failed":
            conditions.append(ListingMonitorItem.is_ordered == 0)
            conditions.append(ListingMonitorItem.order_status == "failed")
        elif order_state == "not_ordered":
            conditions.append(ListingMonitorItem.is_ordered == 0)
            conditions.append(
                or_(
                    ListingMonitorItem.order_status.is_(None),
                    ListingMonitorItem.order_status.notin_(["duplicate", "no_account", "failed"]),
                )
            )
        elif is_ordered is not None:
            conditions.append(ListingMonitorItem.is_ordered == int(is_ordered))
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

        try:
            total = (await self.session.execute(
                select(func.count()).select_from(ListingMonitorItem).where(*conditions)
            )).scalar_one()
            rows = []
            offset = (page - 1) * page_size
            if offset < total:
                stmt = _item_page_statement(conditions, offset, page_size)
                rows = (await self.session.execute(stmt)).all()
        except Exception:
            logger.exception("采集商品查询失败: owner_id={}, page={}, page_size={}", owner_id, page, page_size)
            await self.session.rollback()
            raise

        items = [
            _item_to_dict(item, task_keyword, has_detail=bool(detail_present))
            for item, task_keyword, detail_present in rows
        ]
        return build_pagination_response(items, total, page, page_size)

    async def get_item(self, owner_id: int | None, item_pk: int) -> dict[str, Any] | None:
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
        data = _item_to_dict(item, task_keyword, has_detail=bool(item.detail_json))
        # 附带数据库中存储的原始详情与搜索原始数据（解析为对象，便于前端展示）
        data["detail_json"] = _safe_json_loads(item.detail_json)
        data["raw_json"] = _safe_json_loads(item.raw_json)
        return data

