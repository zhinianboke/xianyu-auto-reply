"""安全管理公共路由边界：鉴权、参数和数据库错误统一HTTP200并保留完整上下文。"""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from common.core.request_meta import format_request_origin
from common.schemas.common import ApiResponse
from common.services.audit_writer import report_safely


class SecurityManagementRoute(APIRoute):
    """安全日志和任务端点共用边界，普通用户不可查询或执行。"""

    failure_message = '安全管理暂不可用，请稍后重试'
    authentication_message = '请先登录后管理安全日志和任务'
    authorization_message = '仅管理员可管理安全日志和任务'
    validation_message = '安全管理参数格式不正确，请检查页码、日期和筛选条件'

    def get_route_handler(self):
        """返回单次请求处理函数，业务失败和依赖失败均明确反馈中文消息。"""
        original = super().get_route_handler()

        async def handle(request: Request):
            """执行管理端请求，文件日志输出失败不能阻断已完成的数据库审计。"""
            try:
                response = await original(request)
            except Exception as exc:
                code, message = 50001, str(exc) if isinstance(exc, RuntimeError) else self.failure_message
                if isinstance(exc, HTTPException):
                    code = 401 if exc.status_code == 401 else 403
                    message = self.authentication_message if code == 401 else self.authorization_message
                elif isinstance(exc, RequestValidationError):
                    code, message = 40001, self.validation_message
                elif isinstance(exc, ValueError):
                    code, message = 40001, str(exc)
                response = JSONResponse(status_code=200, content=ApiResponse(
                    success=False, code=code, message=message, data=None).model_dump())
                try:
                    body = (await request.body()).decode('utf-8', errors='backslashreplace')
                except Exception as body_error:
                    # 断开的请求仍返回原业务错误，并分别记录读取故障，不能由日志读取覆盖结果。
                    body = f'请求体读取失败：{type(body_error).__name__}: {body_error}'
                    report_safely(f'安全管理失败请求体读取异常 method={request.method} url={request.url} '
                                  f'origin={format_request_origin(request.scope)}', body_error)
                report_safely(f'安全管理请求失败 method={request.method} url={request.url} '
                    f'query={request.query_params} headers={dict(request.headers)} '
                    f'body={body} '
                    f'origin={format_request_origin(request.scope)} response_status={response.status_code} '
                    f'response_headers={dict(response.headers)} response_body={response.body.decode("utf-8")}', exc)
            response.headers['Cache-Control'] = 'no-store'
            return response

        return handle
