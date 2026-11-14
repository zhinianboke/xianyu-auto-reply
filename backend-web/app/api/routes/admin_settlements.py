"""管理员用户结算接口：完整访问审计、统一响应、用户分页和单条结果修改。"""
from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.schemas.admin_settlement import AdminSettlementUpdate
from app.services.admin_settlement_service import AdminSettlementService
from common.models.user import User
from common.schemas.common import ApiResponse


class AdminSettlementRoute(APIRoute):
    """在鉴权前记录请求与连接，所有错误以 HTTP 200 和中文业务结果返回。"""

    def get_route_handler(self):
        """包装本模块接口，关联完整请求/响应和业务操作日志。"""
        handler = super().get_route_handler()

        async def settlement_handler(request: Request):
            """处理单次请求；记录拒绝、校验及服务异常，避免错误被静默隐藏。"""
            peer = f"{request.client.host}:{request.client.port}" if request.client else "未知"
            request_id = uuid4().hex
            log = logger.bind(request_id=request_id, operation="admin_settlement", peer=peer)
            request.state.settlement_log = log
            log.info("结算管理请求：request_id={} method={} url={} query={} headers={} body={} 连接对端={} 代理声明X-Forwarded-For={} 代理声明X-Real-IP={}",
                     request_id, request.method, request.url, str(request.query_params), dict(request.headers),
                     (await request.body()).decode("utf-8", errors="replace"), peer,
                     request.headers.get("x-forwarded-for"), request.headers.get("x-real-ip"))
            try:
                response = await handler(request)
            except Exception as exc:
                code = 40001
                if isinstance(exc, RequestValidationError):
                    reasons = [str(item.get("ctx", {}).get("error")) for item in exc.errors()
                               if isinstance(item.get("ctx", {}).get("error"), ValueError)]
                    message = "；".join(dict.fromkeys(reasons)) or "结算参数不正确，请检查编号、分页、结果和文本长度"
                elif isinstance(exc, HTTPException):
                    code = exc.status_code
                    message = {401: "请先登录", 403: "仅管理员可管理结算记录"}.get(code, str(exc.detail))
                elif isinstance(exc, ValueError):
                    message = str(exc)
                else:
                    code, message = 50301, "结算服务暂不可用，请稍后重试"
                log.exception("结算管理失败：request_id={} exception_type={} message={}", request_id, type(exc).__name__, str(exc))
                response = JSONResponse(status_code=200, content=ApiResponse(success=False, code=code, message=message).model_dump())
            response.headers["Cache-Control"] = "no-store"
            write = log.info if json.loads(response.body).get("success") else log.error
            write("结算管理结果：request_id={} status={} headers={} body={}", request_id, response.status_code,
                  dict(response.headers), response.body.decode("utf-8"))
            return response

        return settlement_handler


router = APIRouter(tags=["管理员结算记录"], route_class=AdminSettlementRoute)


@router.get("/users/{user_id}/settlement-records", response_model=ApiResponse)
async def list_user_settlements(
    request: Request,
    user_id: int = Path(ge=1, description="目标用户编号"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """管理员分页查询指定用户记录，使用现有用户隔离逻辑与数据字典。"""
    data = await AdminSettlementService(session, request.state.settlement_log).list_records(user_id, page, page_size)
    return ApiResponse(success=True, message="结算记录查询成功", data=data)


@router.put("/users/{user_id}/settlement-records/{record_id}", response_model=ApiResponse)
async def update_user_settlement(
    payload: AdminSettlementUpdate,
    request: Request,
    user_id: int = Path(ge=1, description="目标用户编号"),
    record_id: int = Path(ge=1, description="结算记录编号"),
    admin: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """逐条修改结果；记录所属用户和原版本必须匹配，返回真实更新记录。"""
    data = await AdminSettlementService(session, request.state.settlement_log).update_result(user_id, record_id, admin.id, payload)
    return ApiResponse(success=True, message="结算结果修改成功", data=data)
