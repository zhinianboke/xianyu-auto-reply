"""
个人发布地址库服务

功能：
1. 提供用户个人地址库的分页查询与增删改（owner_id 数据隔离）
2. 提供按地址文本去重的导入 upsert 能力
3. 为商品发布提供个人地址来源查询
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.user_publish_address import UserPublishAddress
from common.utils.time_utils import safe_isoformat


class UserPublishAddressService:
    """个人发布地址库服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_addresses(
        self,
        owner_id: int,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> Dict[str, Any]:
        """分页查询个人地址库列表。"""
        page = max(page, 1)
        page_size = page_size if page_size in (10, 20, 50, 100) else 20

        conditions = [
            UserPublishAddress.owner_id == owner_id,
            UserPublishAddress.is_deleted.is_(False),
        ]
        normalized_keyword = self._normalize_optional_text(keyword)
        if normalized_keyword:
            conditions.append(UserPublishAddress.address.like(f"%{normalized_keyword}%"))

        count_stmt = select(func.count()).select_from(UserPublishAddress).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(UserPublishAddress)
            .where(*conditions)
            .order_by(
                desc(UserPublishAddress.updated_at),
                desc(UserPublishAddress.id),
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

    async def _find_by_address(self, owner_id: int, address: str) -> UserPublishAddress | None:
        """按地址文本查询本人记录（含软删除行，用于去重）。"""
        stmt = (
            select(UserPublishAddress)
            .where(
                UserPublishAddress.owner_id == owner_id,
                UserPublishAddress.address == address,
            )
            .order_by(desc(UserPublishAddress.id))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(self, owner_id: int, address: str) -> UserPublishAddress:
        """创建个人地址（按地址文本去重，已存在则复活/更新）。"""
        normalized_address = self._normalize_required_text(address, "地址")
        existing = await self._find_by_address(owner_id, normalized_address)
        if existing:
            existing.is_deleted = False
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        record = UserPublishAddress(owner_id=owner_id, address=normalized_address)
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get(self, owner_id: int, address_id: int) -> UserPublishAddress | None:
        """查询本人指定地址。"""
        stmt = select(UserPublishAddress).where(
            UserPublishAddress.id == address_id,
            UserPublishAddress.owner_id == owner_id,
            UserPublishAddress.is_deleted.is_(False),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def update(self, owner_id: int, address_id: int, address: str) -> UserPublishAddress | None:
        """更新个人地址。"""
        record = await self.get(owner_id, address_id)
        if not record:
            return None

        normalized_address = self._normalize_required_text(address, "地址")
        if normalized_address != record.address:
            duplicate = await self._find_by_address(owner_id, normalized_address)
            if duplicate and duplicate.id != record.id and not bool(duplicate.is_deleted):
                raise ValueError("该地址已存在")
            record.address = normalized_address

        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def batch_delete(self, owner_id: int, address_ids: Sequence[int]) -> int:
        """批量软删除个人地址。"""
        normalized_ids: List[int] = []
        for raw_id in address_ids:
            try:
                address_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if address_id > 0 and address_id not in normalized_ids:
                normalized_ids.append(address_id)

        if not normalized_ids:
            raise ValueError("请选择要删除的地址")

        stmt = select(UserPublishAddress).where(
            UserPublishAddress.id.in_(normalized_ids),
            UserPublishAddress.owner_id == owner_id,
            UserPublishAddress.is_deleted.is_(False),
        )
        records = (await self.session.execute(stmt)).scalars().all()
        for record in records:
            record.is_deleted = True

        await self.session.commit()
        return len(records)

    async def upsert_many(self, owner_id: int, addresses: Sequence[str]) -> Dict[str, int]:
        """批量去重导入：已存在则更新（复活），不存在则插入。"""
        created = 0
        updated = 0
        # 同一批内文本去重，避免重复处理
        seen: set[str] = set()
        for raw_address in addresses:
            normalized_address = self._normalize_optional_text(raw_address)
            if not normalized_address or normalized_address in seen:
                continue
            seen.add(normalized_address)

            existing = await self._find_by_address(owner_id, normalized_address)
            if existing:
                if bool(existing.is_deleted):
                    existing.is_deleted = False
                updated += 1
            else:
                self.session.add(UserPublishAddress(owner_id=owner_id, address=normalized_address))
                created += 1

        await self.session.commit()
        return {"created": created, "updated": updated}

    async def list_all_for_owner(self, owner_id: int) -> List[UserPublishAddress]:
        """导出用：查询本人全部有效地址（不分页）。"""
        stmt = (
            select(UserPublishAddress)
            .where(
                UserPublishAddress.owner_id == owner_id,
                UserPublishAddress.is_deleted.is_(False),
            )
            .order_by(desc(UserPublishAddress.updated_at), desc(UserPublishAddress.id))
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def get_enabled_addresses_for_owner(self, owner_id: int) -> List[UserPublishAddress]:
        """发布用：查询本人全部有效个人地址。"""
        if owner_id is None:
            return []
        stmt = (
            select(UserPublishAddress)
            .where(
                UserPublishAddress.owner_id == owner_id,
                UserPublishAddress.is_deleted.is_(False),
            )
            .order_by(desc(UserPublishAddress.updated_at), desc(UserPublishAddress.id))
        )
        return (await self.session.execute(stmt)).scalars().all()

    @staticmethod
    def _normalize_required_text(value: Any, label: str) -> str:
        normalized_value = str(value or "").strip()
        if not normalized_value:
            raise ValueError(f"请填写{label}")
        if len(normalized_value) > 200:
            raise ValueError(f"{label}长度不能超过200个字符")
        return normalized_value

    @staticmethod
    def _normalize_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        normalized_value = str(value).strip()
        if not normalized_value:
            return None
        return normalized_value[:200]


def _address_to_dict(address: UserPublishAddress) -> dict:
    """将个人地址模型转换为字典。"""
    return {
        "id": address.id,
        "address": address.address,
        "use_count": int(address.use_count or 0),
        "last_used_at": safe_isoformat(address.last_used_at),
        "created_at": safe_isoformat(address.created_at),
        "updated_at": safe_isoformat(address.updated_at),
    }
