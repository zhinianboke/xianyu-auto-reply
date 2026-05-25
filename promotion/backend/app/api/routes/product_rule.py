"""
返佣系统 - 选品规则API路由

功能：
1. 选品规则列表查询（分页）
2. 新建选品规则
3. 更新选品规则
4. 删除选品规则
5. 启用/禁用选品规则
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models import User, UserRole

router = APIRouter()


class RuleCreateBody(BaseModel):
    """新建选品规则请求体"""
    rule_name: str = Field(default="", description="规则名称")
    account_id: str = Field(default="", description="闲鱼账号ID")
    cat: str = Field(default="", description="商品类目ID")
    cat_name: str = Field(default="", description="商品类目名称")
    keyword: str = Field(default="", description="商品关键词")
    sort: str = Field(default="default", description="排序规则")
    daily_count: int = Field(default=10, ge=1, description="每天选品条数")
    enabled: bool = Field(default=True, description="是否启用")
    remark: str = Field(default="", description="备注")


class RuleUpdateBody(BaseModel):
    """更新选品规则请求体"""
    rule_name: str | None = Field(default=None, description="规则名称")
    account_id: str | None = Field(default=None, description="闲鱼账号ID")
    cat: str | None = Field(default=None, description="商品类目ID")
    cat_name: str | None = Field(default=None, description="商品类目名称")
    keyword: str | None = Field(default=None, description="商品关键词")
    sort: str | None = Field(default=None, description="排序规则")
    daily_count: int | None = Field(default=None, ge=1, description="每天选品条数")
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
    """分页查询选品规则（管理员可看所有用户数据）"""
    from app.services.product_rule_service import list_rules as do_list
    return await do_list(
        session=session, user_id=current_user.id,
        page=page, page_size=page_size,
        is_admin=(current_user.role == UserRole.ADMIN),
    )


@router.post("/create")
async def create_rule(
    body: RuleCreateBody,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """新建选品规则"""
    from app.services.product_rule_service import create_rule as do_create
    return await do_create(session=session, user_id=current_user.id, data=body.model_dump())


@router.put("/update/{rule_id}")
async def update_rule(
    rule_id: int,
    body: RuleUpdateBody,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """更新选品规则"""
    from app.services.product_rule_service import update_rule as do_update
    # 只传非None的字段
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return await do_update(session=session, user_id=current_user.id, rule_id=rule_id, data=data)


@router.delete("/delete/{rule_id}")
async def delete_rule(
    rule_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """删除选品规则"""
    from app.services.product_rule_service import delete_rule as do_delete
    return await do_delete(session=session, user_id=current_user.id, rule_id=rule_id)


@router.post("/execute/{rule_id}")
async def execute_rule(
    rule_id: int,
    current_user: User = Depends(deps.get_current_active_user),
):
    """手动执行选品规则（不受当日限制）"""
    from app.services.product_rule_scheduler import manual_execute_rule
    return await manual_execute_rule(rule_id=rule_id, user_id=current_user.id)


@router.post("/toggle/{rule_id}")
async def toggle_rule(
    rule_id: int,
    body: ToggleBody,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """启用/禁用选品规则"""
    from app.services.product_rule_service import toggle_rule as do_toggle
    return await do_toggle(session=session, user_id=current_user.id, rule_id=rule_id, enabled=body.enabled)
