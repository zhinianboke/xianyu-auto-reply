"""原管理员定时任务接口：兼容原数组查询及配置操作，新增统一后端分页与安全执行。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.security_management_route import SecurityManagementRoute
from app.services.scheduled_task_management_service import ScheduledTaskManagementService
from common.models.user import User
from common.schemas.common import ApiResponse
from common.services.scheduled_task_query_service import ScheduledTaskQueryService


class ScheduledTaskManagementRoute(SecurityManagementRoute):
    """复用鉴权、HTTP200及完整错误上下文边界，提示使用原任务管理名称。"""

    failure_message = '定时任务管理暂不可用，请稍后重试'
    authentication_message = '请先登录后管理定时任务'
    authorization_message = '仅管理员可管理定时任务'
    validation_message = '定时任务参数格式不正确，请检查页码、每页条数、间隔和启用状态'


router = APIRouter(route_class=ScheduledTaskManagementRoute)
Admin = Annotated[User, Depends(deps.get_current_admin_user)]
Database = Annotated[AsyncSession, Depends(deps.get_db_session)]


@router.get('/scheduled-tasks', response_model=ApiResponse)
async def list_scheduled_tasks(admin: Admin, session: Database,
                               page: int | None = Query(None, ge=1),
                               page_size: int | None = Query(None, ge=1, le=100)):
    """分页参数任一提交即查询同一分页列表；未提交时保留旧任务数组响应。"""
    service = ScheduledTaskQueryService(session)
    data = await service.list_legacy() if page is None and page_size is None else await service.list_page(
        page=page if page is not None else 1, page_size=page_size if page_size is not None else 20)
    return ApiResponse(success=True, code=200, message='定时任务查询成功', data=data)


@router.put('/scheduled-tasks/{task_code}', response_model=ApiResponse)
async def update_scheduled_task(task_code: str, admin: Admin, session: Database,
                                interval_seconds: int | None = None, enabled: bool | None = None):
    """保留原任务代码与查询参数更新接口，不覆盖未提交的配置字段。"""
    result = await ScheduledTaskManagementService(session).update(task_code, interval_seconds, enabled)
    return ApiResponse(success=True, code=200, **result)


@router.post('/scheduled-tasks/{task_code}/trigger', response_model=ApiResponse)
async def trigger_scheduled_task(task_code: str, admin: Admin, session: Database):
    """原手动执行接口统一分派原系统任务与安全频率检查，管理员身份真实传入审计。"""
    result = await ScheduledTaskManagementService(session).trigger(task_code, admin.id)
    return ApiResponse(success=True, code=200, **result)
