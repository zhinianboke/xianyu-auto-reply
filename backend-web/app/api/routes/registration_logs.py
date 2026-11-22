"""注册日志管理员接口：统一中文业务响应、权限校验与组合查询，不提供日志修改或清理。"""
# Loguru 使用花括号格式，并非标准 logging 的百分号占位符。
# ruff: noqa: PLE1205
from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.core.request_meta import format_request_origin
from common.models.user import User
from common.schemas.common import ApiResponse
from common.services.registration_log_query_service import RegistrationLogQueryService


class RegistrationLogRoute(APIRoute):
    """将本模块的参数、鉴权和查询失败统一为 HTTP 200，并记录完整失败上下文。"""

    def get_route_handler(self) -> Callable:
        """包装默认处理器；返回单次请求处理函数，不改变其他日志模块。"""
        handler = super().get_route_handler()

        async def handle(request: Request):
            """处理注册日志查询请求，权限和参数失败均向用户明确反馈。"""
            request_id = getattr(request.state, "request_id", None) or uuid4().hex
            log = logger.bind(request_id=request_id, operation="registration_logs_query")
            origin = format_request_origin(request.scope)
            try:
                response = await handler(request)
            except Exception as exc:  # noqa: BLE001 - 路由边界必须统一记录所有查询及依赖故障。
                code = 40001
                if isinstance(exc, RequestValidationError):
                    message = "注册日志查询参数格式不正确，请检查页码、每页条数和筛选条件"
                elif isinstance(exc, HTTPException):
                    code = 401 if exc.status_code == 401 else 403 if exc.status_code == 403 else 40001
                    message = {401: "请先登录后查看注册日志", 403: "仅管理员可查看注册日志"}.get(
                        code, str(exc.detail)
                    )
                elif isinstance(exc, ValueError):
                    message = str(exc)
                else:
                    code, message = 50301, "注册日志查询暂不可用，请稍后重试"
                log.opt(exception=exc).error(
                    "注册日志查询失败: method={} url={} query={} headers={} body={} origin={} "
                    "exception_type={} exception_message={}",
                    request.method, str(request.url), str(request.query_params), dict(request.headers),
                    (await request.body()).decode("utf-8", errors="replace"), origin,
                    type(exc).__name__, str(exc),
                )
                response = JSONResponse(status_code=200, content=ApiResponse(
                    success=False, code=code, message=message, data=None,
                ).model_dump())
                log.error("注册日志查询失败响应: status={} headers={} body={}",
                          response.status_code, dict(response.headers), response.body.decode("utf-8"))
            else:
                log.info("注册日志查询成功: method={} path={} query={} origin={} status={}",
                         request.method, request.url.path, str(request.query_params), origin, response.status_code)
            response.headers["Cache-Control"] = "no-store"
            return response

        return handle


router = APIRouter(tags=["注册日志"], route_class=RegistrationLogRoute)


@router.get("/registration-logs", response_model=ApiResponse)
async def list_registration_logs(
    _: Annotated[User, Depends(deps.get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(deps.get_db_session)],
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，10/20/50/100"),
    keyword: str | None = Query(None, description="用户名、邮箱或关联用户关键字"),
    client_ip: str | None = Query(None, description="客户端IP或地址片段，按字面包含匹配"),
    operation: str | None = Query(None, description="注册操作 register_submit/register_code"),
    status: str | None = Query(None, description="注册结果 success/failed"),
    start_date: str | None = Query(None, description="开始日期 YYYY-MM-DD，北京时间"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD，北京时间"),
) -> ApiResponse:
    """仅管理员分页查询注册日志，返回日志、计数、分页及数据库中文操作/结果字典。

    Args:
        page/page_size: 页码和规范允许的每页条数。
        keyword/client_ip/operation/status/start_date/end_date: 可组合的独立查询条件。
        _: 统一权限模块认证的管理员。
        session: 当前请求数据库会话。
    Returns:
        HTTP 200 统一成功响应；任何失败由路由包装器转换为中文业务错误。
    """
    data = await RegistrationLogQueryService(session).list_logs(
        keyword=keyword, client_ip=client_ip, operation=operation, status=status,
        start_date=start_date, end_date=end_date, page=page, page_size=page_size,
    )
    return ApiResponse(success=True, code=200, message="注册日志查询成功", data=data)
