"""
黑名单服务

功能：
1. 个人黑名单CRUD操作
2. 闲鱼黑名单查询
3. 新建时自动从订单中获取买家昵称
"""
from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.xy_personal_blacklist import XYPersonalBlacklist
from common.models.xy_platform_blacklist import XYPlatformBlacklist
from common.models.xy_order import XYOrder
from common.models.user import User


class BlacklistService:
    """黑名单服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ==================== 个人黑名单 ====================

    async def list_personal(
        self,
        owner_id: int | None,
        buyer_id: str | None = None,
        buyer_nick: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[XYPersonalBlacklist], int]:
        """查询个人黑名单列表"""
        stmt = select(XYPersonalBlacklist)
        count_stmt = select(func.count(XYPersonalBlacklist.id))

        if owner_id is not None:
            stmt = stmt.where(XYPersonalBlacklist.owner_id == owner_id)
            count_stmt = count_stmt.where(XYPersonalBlacklist.owner_id == owner_id)

        if buyer_id:
            stmt = stmt.where(XYPersonalBlacklist.buyer_id.contains(buyer_id))
            count_stmt = count_stmt.where(XYPersonalBlacklist.buyer_id.contains(buyer_id))

        if buyer_nick:
            stmt = stmt.where(XYPersonalBlacklist.buyer_nick.contains(buyer_nick))
            count_stmt = count_stmt.where(XYPersonalBlacklist.buyer_nick.contains(buyer_nick))

        # 总数
        total = (await self.session.execute(count_stmt)).scalar() or 0

        # 分页
        stmt = stmt.order_by(XYPersonalBlacklist.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def create_personal(
        self,
        owner_id: int,
        buyer_ids: list[str],
        account_id: str | None = None,
        item_id: str | None = None,
        reason: str | None = None,
        is_enabled: bool = True,
    ) -> list[XYPersonalBlacklist]:
        """批量创建个人黑名单（自动判重，已存在的跳过）"""
        # 查询买家昵称
        clean_ids = [bid.strip() for bid in buyer_ids if bid.strip()]
        if not clean_ids:
            return []

        nick_map = await self._get_buyer_nicks(owner_id, clean_ids)

        # 查询已存在的记录用于判重
        # 判重规则：owner_id + buyer_id + account_id + item_id 四元组唯一
        # account_id/item_id 为 None 时用 IS NULL 匹配
        existing_buyer_ids = await self._get_existing_buyer_ids(
            owner_id, clean_ids, account_id, item_id
        )

        created = []
        skipped = 0
        for bid in clean_ids:
            if bid in existing_buyer_ids:
                skipped += 1
                continue
            record = XYPersonalBlacklist(
                owner_id=owner_id,
                account_id=account_id,
                buyer_id=bid,
                buyer_nick=nick_map.get(bid),
                item_id=item_id,
                reason=reason,
                is_enabled=is_enabled,
            )
            self.session.add(record)
            created.append(record)

        await self.session.commit()
        return created

    async def _get_existing_buyer_ids(
        self,
        owner_id: int,
        buyer_ids: list[str],
        account_id: str | None,
        item_id: str | None,
    ) -> set[str]:
        """查询已存在的黑名单记录（用于判重）"""
        stmt = select(XYPersonalBlacklist.buyer_id).where(
            XYPersonalBlacklist.owner_id == owner_id,
            XYPersonalBlacklist.buyer_id.in_(buyer_ids),
        )
        # account_id 判重：None 匹配 IS NULL
        if account_id is None:
            stmt = stmt.where(XYPersonalBlacklist.account_id.is_(None))
        else:
            stmt = stmt.where(XYPersonalBlacklist.account_id == account_id)
        # item_id 判重：None 匹配 IS NULL
        if item_id is None:
            stmt = stmt.where(XYPersonalBlacklist.item_id.is_(None))
        else:
            stmt = stmt.where(XYPersonalBlacklist.item_id == item_id)

        result = await self.session.execute(stmt)
        return {row[0] for row in result.all()}

    async def delete_personal(self, record_id: int, owner_id: int | None) -> bool:
        """删除个人黑名单"""
        stmt = select(XYPersonalBlacklist).where(XYPersonalBlacklist.id == record_id)
        if owner_id is not None:
            stmt = stmt.where(XYPersonalBlacklist.owner_id == owner_id)
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False
        await self.session.delete(record)
        await self.session.commit()
        return True

    async def toggle_personal(self, record_id: int, owner_id: int | None, is_enabled: bool) -> bool:
        """启用/禁用个人黑名单"""
        stmt = select(XYPersonalBlacklist).where(XYPersonalBlacklist.id == record_id)
        if owner_id is not None:
            stmt = stmt.where(XYPersonalBlacklist.owner_id == owner_id)
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False
        record.is_enabled = is_enabled
        await self.session.commit()
        return True

    async def batch_delete_personal(self, ids: list[int], owner_id: int | None) -> int:
        """批量删除个人黑名单"""
        stmt = select(XYPersonalBlacklist).where(XYPersonalBlacklist.id.in_(ids))
        if owner_id is not None:
            stmt = stmt.where(XYPersonalBlacklist.owner_id == owner_id)
        result = await self.session.execute(stmt)
        records = list(result.scalars().all())
        for record in records:
            await self.session.delete(record)
        await self.session.commit()
        return len(records)

    async def _get_buyer_nicks(self, owner_id: int, buyer_ids: list[str]) -> dict[str, str]:
        """从订单表中获取买家昵称"""
        if not buyer_ids:
            return {}

        stmt = (
            select(
                XYOrder.buyer_id,
                func.max(XYOrder.buyer_fish_nick).label("buyer_nick"),
            )
            .where(
                XYOrder.owner_id == owner_id,
                XYOrder.buyer_id.in_(buyer_ids),
                XYOrder.buyer_fish_nick.isnot(None),
                XYOrder.buyer_fish_nick != "",
            )
            .group_by(XYOrder.buyer_id)
        )
        result = await self.session.execute(stmt)
        rows = result.all()
        return {row[0]: row[1] for row in rows if row[0] and row[1]}

    # ==================== 闲鱼黑名单 ====================

    async def list_platform(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """查询闲鱼黑名单列表（含用户名）"""
        count_stmt = select(func.count(XYPlatformBlacklist.id))
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(XYPlatformBlacklist, User.username)
            .outerjoin(User, XYPlatformBlacklist.owner_id == User.id)
            .order_by(XYPlatformBlacklist.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        items = []
        for row in rows:
            record = row[0]
            username = row[1] or ""
            items.append({
                "id": record.id,
                "owner_id": record.owner_id,
                "owner_username": username,
                "buyer_id": record.buyer_id,
                "buyer_nick": record.buyer_nick,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            })

        return items, total
