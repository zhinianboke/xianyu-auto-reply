"""管理员用户管理路由：角色与用户名组合查询、创建、编辑、余额调整和停用。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.services.admin_user_query_service import (
    AdminUserQueryService,
    build_admin_user_payload,
    fetch_user_balances,
)
from app.services.recharge_service import RechargeService
from app.services.user_service import UserService
from common.models.user import User, UserRole, UserStatus
from common.schemas.common import ApiResponse
from common.schemas.user import AdminUserCreate, AdminUserUpdate

router = APIRouter(tags=["admin"])


@router.get("/users")
async def list_users(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    username: str | None = Query(default=None, description="用户名筛选（模糊匹配，忽略大小写）"),
    role: str | None = Query(default=None, description="用户角色筛选（精确匹配）"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """按用户名与角色分页查询用户，返回统一响应并兼容旧客户端顶层列表字段。

    Args:
        limit: 每页条数，范围为 1 至 100。
        offset: 分页偏移量。
        username: 可选用户名关键字。
        role: 可选角色枚举值，空值表示全部角色。
        _: 已校验权限的管理员。
        session: 当前请求的数据库会话。
    Returns:
        统一业务响应；成功时兼容 users、total、limit 和 offset 顶层字段。
    """
    role_value = role.strip() if role else ""
    if role_value and role_value not in {item.value for item in UserRole}:
        return ApiResponse(success=False, code=40001, message="用户角色无效，请选择有效的用户角色").model_dump()
    data = await AdminUserQueryService(session).list(
        limit=limit, offset=offset, username=username,
        role=UserRole(role_value) if role_value else None,
    )
    return {**ApiResponse(success=True, code=200, message="查询成功", data=data).model_dump(), **data}


@router.post("/users", response_model=ApiResponse)
async def create_user(
    payload: AdminUserCreate,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
    user_service: UserService = Depends(deps.get_user_service),
) -> ApiResponse:
    existing_user = await user_service.get_by_username(payload.username)
    if existing_user:
        return ApiResponse(success=False, message="用户名已存在")

    existing_email = await user_service.get_by_email(payload.email)
    if existing_email:
        return ApiResponse(success=False, message="邮箱已存在")

    try:
        user = await user_service.create_admin_user(payload)
    except Exception as exc:
        await session.rollback()
        return ApiResponse(success=False, message=f"创建用户失败: {str(exc)}")

    return ApiResponse(success=True, message="用户创建成功", data={"user": build_admin_user_payload(user)})


@router.put("/users/{user_id}", response_model=ApiResponse)
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    current_admin: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
    user_service: UserService = Depends(deps.get_user_service),
) -> ApiResponse:
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return ApiResponse(success=False, message="请至少填写一个修改项")

    user = await user_service.get(user_id)
    if not user:
        return ApiResponse(success=False, message="用户不存在")

    if current_admin.id == user_id and payload.role is not None and payload.role != UserRole.ADMIN:
        return ApiResponse(success=False, message="当前登录管理员不能取消自己的管理员权限")

    if current_admin.id == user_id and payload.status is not None and payload.status != UserStatus.ACTIVE:
        return ApiResponse(success=False, message="当前登录管理员不能停用自己")

    if payload.username and payload.username != user.username:
        existing_user = await user_service.get_by_username(payload.username)
        if existing_user and existing_user.id != user_id:
            return ApiResponse(success=False, message="用户名已存在")

    if payload.email and payload.email != user.email:
        existing_email = await user_service.get_by_email(payload.email)
        if existing_email and existing_email.id != user_id:
            return ApiResponse(success=False, message="邮箱已存在")

    try:
        updated_user = await user_service.update_admin_user(user, payload)
    except Exception as exc:
        await session.rollback()
        return ApiResponse(success=False, message=f"更新用户失败: {str(exc)}")

    balances = await fetch_user_balances(session, [updated_user.id])
    return ApiResponse(success=True, message="用户更新成功", data={"user": build_admin_user_payload(updated_user, balances=balances)})


class AdminRechargeRequest(BaseModel):
    """管理员手动调整用户余额请求"""
    amount: str = Field(..., description="调整金额，正数为充值，负数为扣减，例如：10.00 或 -5.00")
    remark: str = Field(default="", description="备注（可选）")


@router.post("/users/{user_id}/recharge", response_model=ApiResponse)
async def recharge_user(
    user_id: int,
    payload: AdminRechargeRequest,
    current_admin: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
    user_service: UserService = Depends(deps.get_user_service),
) -> ApiResponse:
    """管理员手动调整指定用户余额（正数充值 / 负数扣减）

    余额调整与流水写入在 RechargeService.manual_recharge 内加行锁防并发，
    并在 service 内部 commit，路由层不重复 commit。
    """
    user = await user_service.get(user_id)
    if not user:
        return ApiResponse(success=False, message="用户不存在")

    service = RechargeService(session)
    result = await service.manual_recharge(
        admin_user_id=current_admin.id,
        target_user_id=user_id,
        amount=payload.amount,
        remark=payload.remark,
    )
    if not result.get("success"):
        return ApiResponse(success=False, message=result.get("message", "余额调整失败"))
    return ApiResponse(success=True, message=result.get("message", "余额调整成功"), data=result.get("data"))


@router.delete("/users/{user_id}", response_model=ApiResponse)
async def delete_user(
    user_id: int,
    current_admin: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
    user_service: UserService = Depends(deps.get_user_service),
) -> ApiResponse:
    if user_id == current_admin.id:
        return ApiResponse(success=False, message="不能停用当前管理员账号")

    user = await user_service.get(user_id)
    if not user:
        return ApiResponse(success=False, message="用户不存在")

    try:
        user.status = UserStatus.INACTIVE
        await session.commit()
    except Exception as exc:
        await session.rollback()
        return ApiResponse(success=False, message=f"停用用户失败: {str(exc)}")

    return ApiResponse(success=True, message="用户已停用")


