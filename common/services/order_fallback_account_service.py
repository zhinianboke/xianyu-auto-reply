"""
用户级兜底下单账号配置服务

功能：
1. 查询/保存当前用户的兜底下单账号配置（每用户仅一条，owner_id 唯一）
2. 供定时下单任务在监控任务无可用下单账号时回退取兜底账号
3. 统一封装数据库操作，避免 SQL 散落各处
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.order_fallback_account import OrderFallbackAccount
from common.models.xy_account import XYAccount
from common.utils.time_utils import safe_isoformat


def _to_dict(record: Optional[OrderFallbackAccount]) -> Dict[str, Any]:
    """将兜底配置模型转换为前端字典；无记录时返回空账号列表。"""
    if not record:
        return {"id": None, "account_ids": [], "created_at": None, "updated_at": None}
    return {
        "id": record.id,
        "account_ids": list(record.account_ids or []),
        "created_at": safe_isoformat(record.created_at),
        "updated_at": safe_isoformat(record.updated_at),
    }


class OrderFallbackAccountService:
    """兜底下单账号配置服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_config(self, owner_id: int, is_admin: bool = False) -> Dict[str, Any]:
        """查询指定用户的兜底下单账号配置（含账号有效性信息）。"""
        record = await self._get_record(owner_id)
        data = _to_dict(record)
        # 附带账号有效性，便于前端提示已失效/已删除的账号
        data["accounts"] = await self._resolve_accounts(owner_id, data["account_ids"], is_admin)
        return data

    async def save_config(self, owner_id: int, account_ids: List[str], is_admin: bool = False) -> Dict[str, Any]:
        """保存（新增或更新）当前用户的兜底下单账号配置。

        - 校验账号必须存在；非管理员还要求账号属于当前用户，管理员可选任意账号；
        - 用户级唯一：存在则更新，不存在则插入。
        """
        cleaned = self._clean_account_ids(account_ids)
        if cleaned:
            valid_ids = await self._filter_valid_account_ids(owner_id, cleaned, is_admin)
            invalid = [aid for aid in cleaned if aid not in valid_ids]
            if invalid:
                if is_admin:
                    raise ValueError(f"以下账号不存在：{('、'.join(invalid))}")
                raise ValueError(f"以下账号不存在或不属于当前用户：{('、'.join(invalid))}")
            cleaned = [aid for aid in cleaned if aid in valid_ids]

        record = await self._get_record(owner_id)
        if record:
            record.account_ids = cleaned
        else:
            record = OrderFallbackAccount(owner_id=owner_id, account_ids=cleaned)
            self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return await self.get_config(owner_id, is_admin)

    async def get_fallback_account_ids(self, owner_id: int) -> List[str]:
        """供定时任务调用：返回指定用户配置的兜底下单账号ID列表。"""
        record = await self._get_record(owner_id)
        if not record:
            return []
        return list(record.account_ids or [])

    # ==================== 内部方法 ====================

    async def _get_record(self, owner_id: int) -> Optional[OrderFallbackAccount]:
        stmt = select(OrderFallbackAccount).where(OrderFallbackAccount.owner_id == owner_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

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

    async def _filter_valid_account_ids(self, owner_id: int, account_ids: List[str], is_admin: bool) -> set[str]:
        """返回 account_ids 中存在的账号ID集合；非管理员还要求账号属于该用户。"""
        conditions = [XYAccount.account_id.in_(account_ids)]
        if not is_admin:
            conditions.append(XYAccount.owner_id == owner_id)
        stmt = select(XYAccount.account_id).where(*conditions)
        return {row[0] for row in (await self.session.execute(stmt)).all()}

    async def _resolve_accounts(self, owner_id: int, account_ids: List[str], is_admin: bool = False) -> List[Dict[str, Any]]:
        """返回每个已配置账号的有效性信息，供前端展示。

        管理员不限账号归属；普通用户仅校验自己名下的账号。
        """
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
