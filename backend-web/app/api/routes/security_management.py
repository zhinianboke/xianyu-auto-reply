"""安全日志与安全任务管理员接口：后端分页、完整详情、手动检查，不提供删除。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.security_management_route import SecurityManagementRoute
from common.models.security_task import SECURITY_TASK_CODE
from common.models.user import User
from common.schemas.common import ApiResponse
from app.services.scheduled_task_management_service import ScheduledTaskManagementService
from common.services.security_query_service import SecurityQueryService

router = APIRouter(route_class=SecurityManagementRoute)
Admin = Annotated[User, Depends(deps.get_current_admin_user)]
Database = Annotated[AsyncSession, Depends(deps.get_db_session)]


@router.get('/security-logs', response_model=ApiResponse)
async def list_logs(admin: Admin, session: Database, page: int = Query(1, ge=1),
                    page_size: int = Query(20, ge=1, le=100), keyword: str | None = None,
                    added_ip: str | None = None, execution_method: str | None = None,
                    result: str | None = None, start_date: str | None = None, end_date: str | None = None):
    """管理员组合筛选安全日志，返回真实记录、计数、分页和数据库中文名称。"""
    data = await SecurityQueryService(session).list_logs(page=page, page_size=page_size, keyword=keyword,
        added_ip=added_ip, execution_method=execution_method, result=result, start_date=start_date, end_date=end_date)
    return ApiResponse(success=True, code=200, message='安全日志查询成功', data=data)


@router.get('/security-logs/{log_id}', response_model=ApiResponse)
async def get_log(log_id: int, admin: Admin, session: Database):
    """管理员读取完整统计、窗口、候选和阈值快照，不截断详情。"""
    return ApiResponse(success=True, code=200, message='安全日志详情读取成功',
                       data=await SecurityQueryService(session).get_log(log_id))


@router.get('/security-tasks', response_model=ApiResponse)
async def list_tasks(admin: Admin, session: Database, page: int = Query(1, ge=1),
                     page_size: int = Query(20, ge=1, le=100)):
    """管理员分页读取安全任务真实下次执行与上次结果。"""
    return ApiResponse(success=True, code=200, message='安全任务查询成功',
                       data=await SecurityQueryService(session).list_tasks(page=page, page_size=page_size))


@router.post('/security-tasks/{task_code}/execute', response_model=ApiResponse)
async def execute_task(task_code: str, admin: Admin, session: Database):
    """管理员手动执行与自动检查共用统计、锁和审计，完成提交后反馈真实结果。"""
    if task_code != SECURITY_TASK_CODE:
        raise ValueError('安全任务不存在')
    result = await ScheduledTaskManagementService(session).trigger(task_code, admin.id)
    return ApiResponse(success=True, code=200, **result)
