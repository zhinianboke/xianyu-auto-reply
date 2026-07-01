"""
用户级兜底采集账号配置服务（按分类）

功能：
1. 按分类查询/新建/修改/删除当前用户的兜底采集账号配置
   （每个用户每个分类一条；category_id=NULL 表示"无分类"全局兜底）
2. 供采集/卖家补全任务在监控任务无可用采集账号时，按 5 层链回退取兜底账号：
   任务账号 → 本用户·本分类 → 本用户·无分类 → 管理员·本分类 → 管理员·无分类
3. 统一封装数据库操作，避免 SQL 散落各处

说明：
- 分类为全局共享维度（名称全局唯一），故"管理员·本分类"直接按同一 category_id 匹配；
- 删除为软删除（is_deleted），重复新建同一分类时复用并恢复原记录；
- MySQL 唯一键对 NULL 不去重，故"无分类"那条由 _get_record 按 IS NULL 复用，保证每用户仅一条。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.collect_fallback_account import CollectFallbackAccount
from common.models.listing_monitor_category import ListingMonitorCategory
from common.models.user import User, UserRole
from common.models.xy_account import XYAccount
from common.utils.time_utils import safe_isoformat


class CollectFallbackAccountService:
    """兜底采集账号配置服务（按分类配置）。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ==================== 前端配置页：查询 ====================

    async def list_configs(self, owner_id: int, is_admin: bool = False) -> List[Dict[str, Any]]:
        """列出兜底采集账号配置（按分类，含无分类那条），附带账号有效性。

        - 普通用户：仅返回本人配置；
        - 管理员：返回全部用户的配置，并附带所属用户名（owner_username）便于区分。
        """
        conditions = [CollectFallbackAccount.is_deleted.is_(False)]
        if not is_admin:
            conditions.append(CollectFallbackAccount.owner_id == owner_id)
        stmt = (
            select(CollectFallbackAccount)
            .where(*conditions)
            .order_by(
                CollectFallbackAccount.owner_id.asc(),
                CollectFallbackAccount.category_id.is_(None).desc(),
                CollectFallbackAccount.id.desc(),
            )
        )
        records = (await self.session.execute(stmt)).scalars().all()
        name_map = await self._category_name_map([r.category_id for r in records])
        # 管理员查看全量时展示配置所属用户名
        owner_name_map = (
            await self._owner_username_map([r.owner_id for r in records]) if is_admin else {}
        )
        result: List[Dict[str, Any]] = []
        for record in records:
            data = self._to_dict(record, name_map, owner_name_map=owner_name_map)
            # 账号有效性按该配置所属用户判定；管理员可引用任意账号
            data["accounts"] = await self._resolve_accounts(
                record.owner_id, data["account_ids"], is_admin
            )
            result.append(data)
        return result

    async def get_config(
        self, owner_id: int, category_id: Optional[int], is_admin: bool = False
    ) -> Dict[str, Any]:
        """查询某个分类的兜底采集账号配置（含账号有效性）。"""
        record = await self._get_record(owner_id, category_id)
        name_map = await self._category_name_map([category_id])
        data = self._to_dict(record, name_map, category_id=category_id)
        data["accounts"] = await self._resolve_accounts(owner_id, data["account_ids"], is_admin)
        return data

    # ==================== 前端配置页：新建/修改/删除 ====================

    async def upsert_config(
        self,
        owner_id: int,
        category_id: Optional[int],
        account_ids: List[str],
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        """新建或修改某个分类的兜底采集账号配置。

        - 同一用户同一分类仅一条；无分类（category_id=NULL）仅一条；
        - 复用软删除记录（重复新建即恢复并覆盖）。
        """
        if category_id is not None:
            category = await self.session.get(ListingMonitorCategory, category_id)
            if not category or category.is_deleted:
                raise ValueError("所选分类不存在")

        cleaned = self._clean_account_ids(account_ids)
        if cleaned:
            valid_ids = await self._filter_valid_account_ids(owner_id, cleaned, is_admin)
            invalid = [aid for aid in cleaned if aid not in valid_ids]
            if invalid:
                if is_admin:
                    raise ValueError(f"以下账号不存在：{('、'.join(invalid))}")
                raise ValueError(f"以下账号不存在或不属于当前用户：{('、'.join(invalid))}")
            cleaned = [aid for aid in cleaned if aid in valid_ids]

        record = await self._get_record(owner_id, category_id, include_deleted=True)
        if record:
            record.account_ids = cleaned
            record.is_deleted = False
        else:
            record = CollectFallbackAccount(
                owner_id=owner_id, category_id=category_id, account_ids=cleaned
            )
            self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return await self.get_config(owner_id, category_id, is_admin)

    async def delete_config(
        self, owner_id: int, category_id: Optional[int], is_admin: bool = False
    ) -> None:
        """软删除某个分类的兜底采集账号配置。"""
        record = await self._get_record(owner_id, category_id)
        if not record:
            raise ValueError("配置不存在")
        record.is_deleted = True
        await self.session.commit()

    # ==================== 定时任务：取生效兜底账号（5 层链） ====================

    async def get_effective_fallback_account_ids(
        self, owner_id: Optional[int], category_id: Optional[int] = None
    ) -> List[str]:
        """返回生效的兜底采集账号ID列表（已按优先级合并去重）。

        顺序：本用户·本分类 → 本用户·无分类 → 管理员·本分类 → 管理员·无分类。
        （任务自身账号由调用方在更前面合并）
        """
        ordered: List[str] = []
        seen: set[str] = set()

        def _add(ids: Optional[List[str]]) -> None:
            for aid in ids or []:
                key = (aid or "").strip()
                if key and key not in seen:
                    seen.add(key)
                    ordered.append(key)

        if owner_id is not None:
            if category_id is not None:
                _add(await self._account_ids_of(owner_id, category_id))
            _add(await self._account_ids_of(owner_id, None))
        if category_id is not None:
            _add(await self._admin_account_ids(category_id))
        _add(await self._admin_account_ids(None))
        return ordered

    # ==================== 内部方法 ====================

    async def _get_record(
        self, owner_id: int, category_id: Optional[int], include_deleted: bool = False
    ) -> Optional[CollectFallbackAccount]:
        conditions = [CollectFallbackAccount.owner_id == owner_id]
        if category_id is None:
            conditions.append(CollectFallbackAccount.category_id.is_(None))
        else:
            conditions.append(CollectFallbackAccount.category_id == category_id)
        if not include_deleted:
            conditions.append(CollectFallbackAccount.is_deleted.is_(False))
        # MySQL 唯一键对 category_id=NULL 不去重，并发新建"无分类"可能产生多条记录；
        # 这里按（未删除优先、id 升序）取最早一条复用，避免 scalar_one_or_none 抛 MultipleResultsFound
        stmt = (
            select(CollectFallbackAccount)
            .where(*conditions)
            .order_by(
                CollectFallbackAccount.is_deleted.asc(),
                CollectFallbackAccount.id.asc(),
            )
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def _account_ids_of(self, owner_id: int, category_id: Optional[int]) -> List[str]:
        record = await self._get_record(owner_id, category_id)
        return list(record.account_ids or []) if record else []

    async def _admin_account_ids(self, category_id: Optional[int]) -> List[str]:
        """返回所有管理员在指定分类（或无分类）下配置的兜底采集账号ID（去重合并）。"""
        admin_ids_subq = select(User.id).where(User.role == UserRole.ADMIN)
        conditions = [
            CollectFallbackAccount.owner_id.in_(admin_ids_subq),
            CollectFallbackAccount.is_deleted.is_(False),
        ]
        if category_id is None:
            conditions.append(CollectFallbackAccount.category_id.is_(None))
        else:
            conditions.append(CollectFallbackAccount.category_id == category_id)
        stmt = select(CollectFallbackAccount.account_ids).where(*conditions)
        result: List[str] = []
        seen: set[str] = set()
        for row in (await self.session.execute(stmt)).all():
            for aid in (row[0] or []):
                if aid and aid not in seen:
                    seen.add(aid)
                    result.append(aid)
        return result

    async def _category_name_map(self, category_ids: List[Optional[int]]) -> Dict[int, str]:
        ids = [cid for cid in set(category_ids) if cid is not None]
        if not ids:
            return {}
        stmt = select(ListingMonitorCategory.id, ListingMonitorCategory.name).where(
            ListingMonitorCategory.id.in_(ids)
        )
        return {row[0]: row[1] for row in (await self.session.execute(stmt)).all()}

    def _to_dict(
        self,
        record: Optional[CollectFallbackAccount],
        name_map: Dict[int, str],
        category_id: Optional[int] = None,
        owner_name_map: Optional[Dict[int, str]] = None,
    ) -> Dict[str, Any]:
        """将兜底配置模型转换为前端字典；无记录时返回空账号列表。"""
        owner_name_map = owner_name_map or {}
        if not record:
            return {
                "id": None,
                "owner_id": None,
                "owner_username": None,
                "category_id": category_id,
                "category_name": name_map.get(category_id) if category_id is not None else None,
                "account_ids": [],
                "created_at": None,
                "updated_at": None,
            }
        cid = record.category_id
        return {
            "id": record.id,
            "owner_id": record.owner_id,
            "owner_username": owner_name_map.get(record.owner_id),
            "category_id": cid,
            "category_name": name_map.get(cid) if cid is not None else None,
            "account_ids": list(record.account_ids or []),
            "created_at": safe_isoformat(record.created_at),
            "updated_at": safe_isoformat(record.updated_at),
        }

    async def _owner_username_map(self, owner_ids: List[Optional[int]]) -> Dict[int, str]:
        """批量查询配置所属用户名（管理员查看全量时展示）。"""
        ids = [oid for oid in set(owner_ids) if oid is not None]
        if not ids:
            return {}
        stmt = select(User.id, User.username).where(User.id.in_(ids))
        return {row[0]: row[1] for row in (await self.session.execute(stmt)).all()}

    @staticmethod
    def _clean_account_ids(account_ids: Optional[List[str]]) -> List[str]:
        """去重去空并保持原有顺序。"""
        result: List[str] = []
        seen: set[str] = set()
        for aid in account_ids or []:
            key = (aid or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(key)
        return result

    async def _filter_valid_account_ids(
        self, owner_id: int, account_ids: List[str], is_admin: bool
    ) -> set[str]:
        """返回 account_ids 中存在的账号ID集合；非管理员还要求账号属于该用户。"""
        conditions = [XYAccount.account_id.in_(account_ids)]
        if not is_admin:
            conditions.append(XYAccount.owner_id == owner_id)
        stmt = select(XYAccount.account_id).where(*conditions)
        return {row[0] for row in (await self.session.execute(stmt)).all()}

    async def _resolve_accounts(
        self, owner_id: int, account_ids: List[str], is_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """返回每个已配置账号的有效性信息，供前端展示。"""
        if not account_ids:
            return []
        conditions = [XYAccount.account_id.in_(account_ids)]
        if not is_admin:
            conditions.append(XYAccount.owner_id == owner_id)
        stmt = select(XYAccount.account_id, XYAccount.status, XYAccount.cookie).where(*conditions)
        rows = {row[0]: (row[1], row[2]) for row in (await self.session.execute(stmt)).all()}
        result: List[Dict[str, Any]] = []
        for aid in account_ids:
            if aid not in rows:
                result.append({"account_id": aid, "valid": False, "reason": "账号不存在或已删除"})
                continue
            status, cookie = rows[aid]
            status_norm = (status or "active").strip().lower()
            if not cookie:
                result.append({"account_id": aid, "valid": False, "reason": "未登录(Cookie为空)"})
            elif status_norm in {"inactive", "disabled", "suspended", "deleted"}:
                result.append({"account_id": aid, "valid": False, "reason": f"已停用(状态={status_norm})"})
            else:
                result.append({"account_id": aid, "valid": True, "reason": None})
        return result
