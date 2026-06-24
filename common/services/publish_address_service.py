"""
公共商品发布随机地址池服务

功能：
1. 提供随机地址池分页查询与维护能力
2. 提供发布执行前的地址解析与批量随机分配
3. 提供地址池可用账号选项查询
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.publish_address import PublishAddress
from common.models.user_publish_address import UserPublishAddress
from common.models.xy_account import XYAccount
from common.services.user_publish_address_service import UserPublishAddressService
from common.utils.time_utils import get_beijing_now_naive, safe_isoformat


@dataclass
class ResolvedPublishAddress:
    """发布前解析出的最终地址信息。"""

    resolved_address_id: int | None
    resolved_address_text: str
    address_source: str
    address_expected_text: str | None = None

    def apply_to_item_data(self, item_data: dict) -> dict:
        """将解析结果写入本次发布商品数据。"""
        next_item_data = dict(item_data)
        next_item_data["address"] = self.resolved_address_text
        if self.address_expected_text:
            next_item_data["address_expected_text"] = self.address_expected_text
        else:
            next_item_data.pop("address_expected_text", None)
        return next_item_data

    def to_log_fields(self) -> dict:
        """转换为发布日志字段。"""
        return {
            "resolved_address_id": self.resolved_address_id,
            "resolved_address_text": self.resolved_address_text,
            "address_source": self.address_source,
        }


@dataclass
class PublishAddressQueueState:
    """批量发布时的地址随机队列状态。

    addresses/queue 中的元素可能是全局地址 PublishAddress 或个人地址 UserPublishAddress。
    """

    addresses: List[Any]
    address_source: str
    queue: List[Any] = field(default_factory=list)
    last_selected_id: int | None = None


class PublishAddressService:
    """商品发布随机地址池服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_addresses(
        self,
        owner_id: int | None,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        account_id: str | None = None,
        is_enabled: bool | None = None,
    ) -> Dict[str, Any]:
        """分页查询随机地址池列表。"""
        page = max(page, 1)
        page_size = page_size if page_size in (10, 20, 50, 100) else 20
        conditions = self._build_list_conditions(
            owner_id=owner_id,
            owned_account_ids=[],
            keyword=keyword,
            account_id=account_id,
            is_enabled=is_enabled,
        )

        count_stmt = select(func.count()).select_from(PublishAddress).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(PublishAddress)
            .where(*conditions)
            .order_by(
                desc(PublishAddress.last_used_at),
                desc(PublishAddress.updated_at),
                desc(PublishAddress.id),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        return {
            "list": [_address_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }

    async def list_account_options(self, owner_id: int | None) -> List[dict]:
        """查询地址池账号选项。"""
        return []

    async def create(self, operator_user_id: int, data: dict) -> PublishAddress:
        """创建随机地址。"""
        payload = await self._normalize_payload(data, partial=False)
        address = PublishAddress(
            created_by=operator_user_id,
            **payload,
        )
        self.session.add(address)
        await self.session.commit()
        await self.session.refresh(address)
        return address

    async def get(self, address_id: int) -> PublishAddress | None:
        """根据主键查询随机地址。"""
        stmt = select(PublishAddress).where(PublishAddress.id == address_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def update(self, address_id: int, data: dict) -> PublishAddress | None:
        """更新随机地址。"""
        address = await self.get(address_id)
        if not address or not bool(address.is_enabled):
            return None

        payload = await self._normalize_payload(data, partial=True)
        for field_name, field_value in payload.items():
            setattr(address, field_name, field_value)

        await self.session.commit()
        await self.session.refresh(address)
        return address

    async def batch_delete(self, address_ids: Sequence[int]) -> int:
        """批量软删除随机地址。"""
        normalized_ids: List[int] = []
        for raw_address_id in address_ids:
            try:
                address_id = int(raw_address_id)
            except (TypeError, ValueError):
                continue
            if address_id > 0 and address_id not in normalized_ids:
                normalized_ids.append(address_id)

        if not normalized_ids:
            raise ValueError("请选择要删除的随机地址")

        stmt = select(PublishAddress).where(
            PublishAddress.id.in_(normalized_ids),
            PublishAddress.is_enabled.is_(True),
        )
        addresses = (await self.session.execute(stmt)).scalars().all()
        for address in addresses:
            address.is_enabled = False

        await self.session.commit()
        return len(addresses)

    async def update_status(self, address_id: int, is_enabled: bool) -> PublishAddress | None:
        """更新随机地址启用状态。"""
        address = await self.get(address_id)
        if not address:
            return None
        address.is_enabled = bool(is_enabled)
        await self.session.commit()
        await self.session.refresh(address)
        return address

    async def get_owned_account_ids(self, owner_id: int | None) -> List[str]:
        """查询用户可访问的账号ID列表。"""
        if owner_id is None:
            return []
        stmt = select(XYAccount.account_id).where(XYAccount.owner_id == owner_id)
        result = await self.session.execute(stmt)
        return [str(account_id) for account_id in result.scalars().all() if account_id]

    async def _list_enabled_addresses(self, account_id: str | None) -> List[PublishAddress]:
        stmt = (
            select(PublishAddress)
            .where(PublishAddress.is_enabled.is_(True))
            .order_by(desc(PublishAddress.updated_at), desc(PublishAddress.id))
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def _get_account_owner_id(self, account_id: str) -> int | None:
        """根据账号ID查询其归属用户ID。"""
        stmt = select(XYAccount.owner_id).where(XYAccount.account_id == account_id).limit(1)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def build_queue_state(self, account_id: str) -> PublishAddressQueueState:
        """为指定账号构建随机地址队列状态。

        优先使用该账号归属用户的个人地址库；个人库为空时回退到全局随机地址库。
        """
        owner_id = await self._get_account_owner_id(account_id)
        if owner_id is not None:
            personal_svc = UserPublishAddressService(self.session)
            personal_addresses = await personal_svc.get_enabled_addresses_for_owner(owner_id)
            if personal_addresses:
                return PublishAddressQueueState(
                    addresses=personal_addresses,
                    address_source="personal_pool",
                )

        global_addresses = await self._list_enabled_addresses(account_id=None)
        return PublishAddressQueueState(
            addresses=global_addresses,
            address_source="global_pool",
        )

    async def resolve_publish_address(
        self,
        account_id: str,
        item_data: dict,
        queue_state: PublishAddressQueueState | None = None,
    ) -> ResolvedPublishAddress:
        """解析单个商品本次发布要使用的最终地址。"""
        current_queue_state = queue_state or await self.build_queue_state(account_id)
        if not current_queue_state.addresses:
            raise ValueError("随机地址库中没有可用地址，无法自动分配宝贝所在地")

        if not current_queue_state.queue:
            current_queue_state.queue = self._build_weighted_queue(
                current_queue_state.addresses,
                current_queue_state.last_selected_id,
            )

        selected_address = current_queue_state.queue.pop(0)
        current_queue_state.last_selected_id = selected_address.id
        self.mark_address_used(selected_address)
        return ResolvedPublishAddress(
            resolved_address_id=selected_address.id,
            resolved_address_text=self._address_text(selected_address),
            address_source=current_queue_state.address_source,
            address_expected_text=None,
        )

    @staticmethod
    def _address_text(address: Any) -> str:
        """读取地址对象的搜索文本，兼容全局地址与个人地址两种模型。"""
        if isinstance(address, UserPublishAddress):
            return address.address
        return address.search_keyword

    def mark_address_used(self, address: PublishAddress) -> None:
        """记录地址被分配使用。"""
        address.use_count = int(address.use_count or 0) + 1
        address.last_used_at = get_beijing_now_naive()

    async def _normalize_payload(self, data: dict, partial: bool) -> dict:
        payload: dict = {}
        address_value = None
        for field_name in ("address", "search_keyword", "name"):
            if field_name in data:
                address_value = data.get(field_name)
                break

        if address_value is None:
            if partial:
                return payload
            raise ValueError("请填写地址")

        normalized_address = self._normalize_required_text(address_value, "地址")
        payload["name"] = normalized_address
        payload["search_keyword"] = normalized_address
        payload["expected_text"] = None
        payload["account_id"] = None
        payload["weight"] = 1
        payload["sort_order"] = 100
        payload["is_enabled"] = True
        payload["remark"] = None
        return payload

    async def _ensure_account_exists(self, account_id: str) -> None:
        stmt = select(func.count()).select_from(XYAccount).where(XYAccount.account_id == account_id)
        exists = (await self.session.execute(stmt)).scalar() or 0
        if exists <= 0:
            raise ValueError("指定账号不存在，请重新选择")

    def _build_list_conditions(
        self,
        owner_id: int | None,
        owned_account_ids: Sequence[str],
        keyword: str | None,
        account_id: str | None,
        is_enabled: bool | None,
    ) -> List[Any]:
        normalized_is_enabled = True if is_enabled is None else bool(is_enabled)
        conditions: List[Any] = [PublishAddress.is_enabled.is_(normalized_is_enabled)]
        normalized_keyword = self._normalize_optional_text(keyword)
        if normalized_keyword:
            keyword_like = f"%{normalized_keyword}%"
            conditions.append(
                or_(
                    PublishAddress.name.like(keyword_like),
                    PublishAddress.search_keyword.like(keyword_like),
                )
            )
        return conditions

    def _build_weighted_queue(
        self,
        addresses: Sequence[PublishAddress],
        last_selected_id: int | None,
    ) -> List[PublishAddress]:
        queue = list(addresses)
        random.shuffle(queue)

        if last_selected_id and len(queue) > 1 and queue[0].id == last_selected_id:
            queue[0], queue[1] = queue[1], queue[0]
        return queue

    @staticmethod
    def _normalize_required_text(value: Any, label: str) -> str:
        normalized_value = str(value or "").strip()
        if not normalized_value:
            raise ValueError(f"请填写{label}")
        return normalized_value

    @staticmethod
    def _normalize_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        normalized_value = str(value).strip()
        return normalized_value or None

    @staticmethod
    def _normalize_positive_int(value: Any, label: str, min_value: int, max_value: int) -> int:
        try:
            normalized_value = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}格式不正确") from exc
        if normalized_value < min_value or normalized_value > max_value:
            raise ValueError(f"{label}必须在 {min_value} 到 {max_value} 之间")
        return normalized_value


def _address_to_dict(address: PublishAddress) -> dict:
    """将地址池模型转换为字典。"""
    return {
        "id": address.id,
        "address": address.search_keyword,
        "name": address.name,
        "search_keyword": address.search_keyword,
        "expected_text": address.expected_text,
        "account_id": address.account_id,
        "weight": int(address.weight or 1),
        "sort_order": int(address.sort_order or 100),
        "is_enabled": bool(address.is_enabled),
        "use_count": int(address.use_count or 0),
        "last_used_at": safe_isoformat(address.last_used_at),
        "created_by": address.created_by,
        "remark": address.remark,
        "created_at": safe_isoformat(address.created_at),
        "updated_at": safe_isoformat(address.updated_at),
    }
