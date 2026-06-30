"""
用户级兜底私信账号配置接口（按分类）

功能：
1. 列出当前用户已配置的兜底私信账号（按分类，含无分类那条）
2. 新建/修改某个分类的兜底私信账号配置（每用户每分类一条；无分类仅一条）
3. 删除某个分类的兜底私信账号配置（软删除）

说明：当私信任务发现商品下单账号发私信不可用时，按链回退：
下单账号 → 本用户·本分类 → 本用户·无分类 → 管理员·本分类 → 管理员·无分类。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db_session
from common.models.user import User
from common.schemas.common import ApiResponse
from common.services.dm_fallback_account_service import DmFallbackAccountService
from common.utils.auth_scope import is_admin_user

router = APIRouter(prefix="/product-monitor/dm-fallback-accounts", tags=["兜底私信账号"])


class DmFallbackAccountSaveRequest(BaseModel):
    """保存兜底私信账号配置请求（按分类）"""

    category_id: Optional[int] = Field(None, description="所属分类ID（不传=无分类全局兜底）")
    account_ids: List[str] = Field(default_factory=list, description="兜底私信账号ID列表（可多选，可为空）")


def _resolve_owner_id(current_user: User) -> int:
    """兜底配置为用户级数据：管理员同样按自身ID存储，其配置即作为"管理员兜底"层。"""
    return current_user.id


@router.get("", response_model=ApiResponse)
async def list_dm_fallback_accounts(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """列出当前用户已配置的兜底私信账号（按分类）"""
    svc = DmFallbackAccountService(session)
    data = await svc.list_configs(_resolve_owner_id(current_user), is_admin_user(current_user))
    return ApiResponse(success=True, message="查询成功", data=data)


@router.put("", response_model=ApiResponse)
async def upsert_dm_fallback_accounts(
    req: DmFallbackAccountSaveRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """新建或修改某个分类的兜底私信账号配置"""
    svc = DmFallbackAccountService(session)
    try:
        data = await svc.upsert_config(
            _resolve_owner_id(current_user),
            req.category_id,
            req.account_ids,
            is_admin_user(current_user),
        )
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    return ApiResponse(success=True, message="兜底私信账号保存成功", data=data)


@router.delete("", response_model=ApiResponse)
async def delete_dm_fallback_accounts(
    category_id: Optional[int] = Query(None, description="所属分类ID（不传=删除无分类那条）"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """删除某个分类的兜底私信账号配置（软删除）"""
    svc = DmFallbackAccountService(session)
    try:
        await svc.delete_config(_resolve_owner_id(current_user), category_id, is_admin_user(current_user))
    except ValueError as exc:
        return ApiResponse(success=False, message=str(exc))
    return ApiResponse(success=True, message="删除成功")
