"""
在线安装 HTTP 接口。

功能：无需登录测试 SSH、创建后台任务及增量读取真实日志，访客会话隔离任务。
所有请求（含拒绝及参数错误）记录连接对端和业务结果。
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from loguru import logger

from app.api.online_install_access import get_online_install_scope
from app.schemas.online_install import OnlineInstallRequest, SSHConnectionRequest
from app.services.online_install_service import (
    execute_install_task,
    get_install_logs,
    prepare_install_task,
)
from app.services.online_install_ssh import OnlineInstallError, test_ssh_connection
from common.schemas.common import ApiResponse
from common.utils.http_utils import get_client_ip

FIELD_LABELS = {
    "host": "服务器地址", "port": "SSH 端口", "username": "SSH 用户名",
    "password": "SSH 密码", "task_id": "安装任务编号",
    "auth_method": "SSH 认证方式", "private_key": "SSH 私钥", "private_key_passphrase": "私钥口令",
    "cursor": "日志读取位置",
    "X-Install-Session": "安装会话标识",
}


class OnlineInstallRoute(APIRoute):
    """本功能统一访问日志与异常响应，保持每个 HTTP 请求返回 200 和中文业务提示。"""

    def get_route_handler(self) -> Callable:
        """包装默认处理器，在权限和参数校验之前记录本次连接与完整请求。"""
        handler = super().get_route_handler()

        async def logged_handler(request: Request) -> Response:
            """记录原始请求及失败响应，保持前端可以直接展示业务 message。"""
            peer = f"{request.client.host}:{request.client.port}" if request.client else "-"
            log = logger.bind(request_id=uuid4().hex, operation="online_install", peer=peer)
            request.state.online_install_log = log
            log.info(
                f"[在线安装] 请求：method={request.method} url={request.url} query={request.query_params!s} "
                f"headers={dict(request.headers)} body={(await request.body()).decode('utf-8', errors='replace')} "
                f"连接对端={peer} 代理声明X-Forwarded-For={request.headers.get('x-forwarded-for')} "
                f"代理声明X-Real-IP={request.headers.get('x-real-ip')} 客户端IP声明={get_client_ip(request)}"
            )
            try:
                response = await handler(request)
            except RequestValidationError as exc:
                messages = []
                for error in exc.errors():
                    detail = error.get("ctx", {}).get("error")
                    field = FIELD_LABELS.get(str(error["loc"][-1]), "提交参数")
                    messages.append(str(detail) if isinstance(detail, ValueError) else f"{field}填写不正确，请检查后重试")
                log.exception(f"[在线安装] 参数错误：{exc.errors()}")
                response = JSONResponse(
                    status_code=200,
                    content=ApiResponse(success=False, code=40001, message="；".join(dict.fromkeys(messages))).model_dump(),
                )
            except HTTPException as exc:
                message = str(exc.detail)
                log.exception(f"[在线安装] 权限拒绝：code={exc.status_code} detail={exc.detail}")
                response = JSONResponse(status_code=200, content=ApiResponse(success=False, code=exc.status_code, message=message).model_dump())
            except OnlineInstallError as exc:
                log.exception(f"[在线安装] 操作失败：exception_type={type(exc).__name__}")
                response = JSONResponse(status_code=200, content=ApiResponse(success=False, code=40001, message=str(exc)).model_dump())
            except Exception as exc:
                log.exception(f"[在线安装] 服务异常：exception_type={type(exc).__name__}")
                response = JSONResponse(status_code=200, content=ApiResponse(success=False, code=50301, message="在线安装服务暂不可用，请稍后重试").model_dump())
            response.headers["Cache-Control"] = "no-store"
            result = response.body.decode("utf-8")
            write_result = log.info if json.loads(result).get("success") else log.error
            write_result(f"[在线安装] 处理结果：status={response.status_code} headers={dict(response.headers)} body={result}")
            return response

        return logged_handler


router = APIRouter(prefix="/online-install", tags=["在线安装"], route_class=OnlineInstallRoute)


@router.post("/test-ssh", response_model=ApiResponse)
async def test_connection(
    connection: SSHConnectionRequest, request: Request,
    scope_id: str = Depends(get_online_install_scope),
) -> ApiResponse:
    """无需登录，仅测试所选 SSH 认证方式，返回真实服务器 SSH 版本。"""
    request.state.online_install_log.info(f"[在线安装] 测试连接：scope={scope_id} target={connection.host}:{connection.port}")
    data = await asyncio.to_thread(test_ssh_connection, connection)
    return ApiResponse(success=True, code=200, message="SSH 连接测试成功", data=data)


@router.post("/tasks/{task_id}", response_model=ApiResponse)
async def start_install(
    task_id: UUID, connection: OnlineInstallRequest,
    request: Request, background_tasks: BackgroundTasks,
    scope_id: str = Depends(get_online_install_scope),
) -> ApiResponse:
    """幂等创建访客安装任务，响应发送后直接执行脚本；仅新任务安排后台执行。"""
    log = request.state.online_install_log
    data, lock = await prepare_install_task(scope_id, task_id, connection, log)
    if lock is not None:
        background_tasks.add_task(execute_install_task, scope_id, task_id, connection, lock, log)
    return ApiResponse(success=True, code=200, message="安装任务已提交，请查看安装日志", data=data)


@router.get("/tasks/{task_id}/logs", response_model=ApiResponse)
async def read_logs(
    task_id: UUID, scope_id: str = Depends(get_online_install_scope),
    cursor: int = Query(default=0, ge=0, description="已读取的日志段数"),
) -> ApiResponse:
    """按访客会话及游标读取服务器输出，任务失败作为真实 data 结果展示。"""
    data = await get_install_logs(scope_id, task_id, cursor)
    return ApiResponse(success=True, code=200, message="安装日志读取成功", data=data)
