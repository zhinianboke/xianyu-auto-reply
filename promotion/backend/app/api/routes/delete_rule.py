"""
返佣系统 - 删除规则API路由

功能：
1. 删除规则列表查询（分页）
2. 新建删除规则
3. 更新删除规则
4. 删除删除规则
5. 启用/禁用删除规则
6. 查询用户的闲鱼账号列表（供下拉选择）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models import User, UserRole

router = APIRouter()


class DeleteRuleCreateBody(BaseModel):
    """新建删除规则请求体"""
    rule_name: str = Field(default="", description="规则名称")
    account_id: str = Field(description="闲鱼账号ID")
    daily_count: int = Field(default=5, ge=1, description="每天删除数量")
    min_publish_days: int = Field(default=7, ge=1, description="发布满多少天才能删除")
    enabled: bool = Field(default=True, description="是否启用")
    remark: str = Field(default="", description="备注")


class DeleteRuleUpdateBody(BaseModel):
    """更新删除规则请求体"""
    rule_name: str | None = Field(default=None, description="规则名称")
    account_id: str | None = Field(default=None, description="闲鱼账号ID")
    daily_count: int | None = Field(default=None, ge=1, description="每天删除数量")
    min_publish_days: int | None = Field(default=None, ge=1, description="发布满多少天才能删除")
    enabled: bool | None = Field(default=None, description="是否启用")
    remark: str | None = Field(default=None, description="备注")


class ToggleBody(BaseModel):
    """启用/禁用请求体"""
    enabled: bool = Field(description="是否启用")


@router.get("/list")
async def list_rules(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """分页查询删除规则（管理员可看所有用户数据）"""
    from app.services.delete_rule_service import list_rules as do_list
    return await do_list(
        session=session, user_id=current_user.id,
        page=page, page_size=page_size,
        is_admin=(current_user.role == UserRole.ADMIN),
    )


@router.post("/create")
async def create_rule(
    body: DeleteRuleCreateBody,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """新建删除规则"""
    from app.services.delete_rule_service import create_rule as do_create
    return await do_create(session=session, user_id=current_user.id, data=body.model_dump())


@router.put("/update/{rule_id}")
async def update_rule(
    rule_id: int,
    body: DeleteRuleUpdateBody,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """更新删除规则"""
    from app.services.delete_rule_service import update_rule as do_update
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return await do_update(session=session, user_id=current_user.id, rule_id=rule_id, data=data)


@router.delete("/delete/{rule_id}")
async def delete_rule(
    rule_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """删除删除规则"""
    from app.services.delete_rule_service import delete_rule as do_delete
    return await do_delete(session=session, user_id=current_user.id, rule_id=rule_id)


@router.post("/toggle/{rule_id}")
async def toggle_rule(
    rule_id: int,
    body: ToggleBody,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """启用/禁用删除规则"""
    from app.services.delete_rule_service import toggle_rule as do_toggle
    return await do_toggle(session=session, user_id=current_user.id, rule_id=rule_id, enabled=body.enabled)


@router.get("/xy-accounts")
async def list_xy_accounts(
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """查询用户的闲鱼账号列表（供删除规则选择使用）"""
    from common.models.xy_account import XYAccount

    stmt = select(XYAccount).where(
        XYAccount.owner_id == current_user.id,
        XYAccount.status == "active",
    ).order_by(XYAccount.id.asc())
    result = await session.execute(stmt)
    accounts = result.scalars().all()

    return {
        "success": True,
        "data": [
            {
                "account_id": a.account_id,
                "display_name": a.display_name or a.account_id,
            }
            for a in accounts
        ],
    }
