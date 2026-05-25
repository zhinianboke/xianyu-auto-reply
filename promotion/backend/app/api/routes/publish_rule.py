"""
返佣系统 - 发布规则API路由

功能：
1. 发布规则列表查询（分页）
2. 新建发布规则
3. 更新发布规则
4. 删除发布规则
5. 启用/禁用发布规则
6. 手动执行发布规则
7. 查询用户的闲鱼账号列表（供下拉选择）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models import User, UserRole

router = APIRouter()


class PublishRuleCreateBody(BaseModel):
    """新建发布规则请求体"""
    rule_name: str = Field(default="", description="规则名称")
    account_id: str = Field(description="闲鱼账号ID")
    daily_count: int = Field(default=5, ge=1, description="每天发布数量")
    enabled: bool = Field(default=True, description="是否启用")
    remark: str = Field(default="", description="备注")


class PublishRuleUpdateBody(BaseModel):
    """更新发布规则请求体"""
    rule_name: str | None = Field(default=None, description="规则名称")
    account_id: str | None = Field(default=None, description="闲鱼账号ID")
    daily_count: int | None = Field(default=None, ge=1, description="每天发布数量")
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
    """分页查询发布规则（管理员可看所有用户数据）"""
    from app.services.publish_rule_service import list_rules as do_list
    return await do_list(
        session=session, user_id=current_user.id,
        page=page, page_size=page_size,
        is_admin=(current_user.role == UserRole.ADMIN),
    )


@router.post("/create")
async def create_rule(
    body: PublishRuleCreateBody,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """新建发布规则"""
    from app.services.publish_rule_service import create_rule as do_create
    return await do_create(session=session, user_id=current_user.id, data=body.model_dump())


@router.put("/update/{rule_id}")
async def update_rule(
    rule_id: int,
    body: PublishRuleUpdateBody,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """更新发布规则"""
    from app.services.publish_rule_service import update_rule as do_update
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return await do_update(session=session, user_id=current_user.id, rule_id=rule_id, data=data)


@router.delete("/delete/{rule_id}")
async def delete_rule(
    rule_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """删除发布规则"""
    from app.services.publish_rule_service import delete_rule as do_delete
    return await do_delete(session=session, user_id=current_user.id, rule_id=rule_id)


@router.post("/toggle/{rule_id}")
async def toggle_rule(
    rule_id: int,
    body: ToggleBody,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """启用/禁用发布规则"""
    from app.services.publish_rule_service import toggle_rule as do_toggle
    return await do_toggle(session=session, user_id=current_user.id, rule_id=rule_id, enabled=body.enabled)


@router.post("/execute/{rule_id}")
async def execute_rule(
    rule_id: int,
    current_user: User = Depends(deps.get_current_active_user),
):
    """手动执行发布规则（不受当日限制）"""
    from app.services.publish_rule_scheduler import manual_execute_publish_rule
    return await manual_execute_publish_rule(rule_id=rule_id, user_id=current_user.id)


@router.get("/execute-status/{task_id}")
async def get_execute_rule_status(
    task_id: str,
    current_user: User = Depends(deps.get_current_active_user),
):
    """查询手动执行发布规则的后台任务状态"""
    from app.services.publish_rule_scheduler import get_manual_execute_publish_rule_status
    return await get_manual_execute_publish_rule_status(task_id=task_id, user_id=current_user.id)


@router.get("/xy-accounts")
async def list_xy_accounts(
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """查询用户的闲鱼账号列表（供发布规则选择使用）"""
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
