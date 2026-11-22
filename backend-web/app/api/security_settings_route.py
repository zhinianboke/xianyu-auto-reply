"""安全设置路由边界：管理员鉴权与参数错误使用中文统一业务响应。"""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from loguru import logger

from common.core.request_meta import format_request_origin
from common.schemas.common import ApiResponse


class SecuritySettingsRoute(APIRoute):
    """仅处理专用安全设置接口，不改变其他历史系统设置端点的响应契约。"""

    def get_route_handler(self):
        """返回请求处理器，依赖与参数异常也转换为 HTTP 200 中文失败。"""
        original = super().get_route_handler()
        if self.path.rsplit('/', 1)[-1] != 'security':
            return original

        async def handler(request: Request):
            """调用安全设置端点并完整记录鉴权、模型或依赖故障。"""
            try:
                response = await original(request)
            except Exception as exc:  # noqa: BLE001 - 安全设置边界不得泄漏英文错误或静默失败
                code, message = 50001, '安全设置暂不可用，请稍后重试'
                if isinstance(exc, HTTPException):
                    code = 401 if exc.status_code == 401 else 403 if exc.status_code == 403 else 40001
                    message = {401: '请先登录后管理安全设置', 403: '仅管理员可管理安全设置'}.get(code, str(exc.detail))
                elif isinstance(exc, RequestValidationError):
                    code, message = 40001, '安全设置参数格式不正确，请检查填写内容'
                response = JSONResponse(status_code=200, content=ApiResponse(
                    success=False, code=code, message=message, data=None,
                ).model_dump())
                logger.opt(exception=exc).error(
                    '安全设置请求失败：method={} url={} query={} headers={} body={} origin={} '
                    'response_status={} response_headers={} response_body={}',
                    request.method, str(request.url), str(request.query_params), dict(request.headers),
                    (await request.body()).decode('utf-8', errors='backslashreplace'),
                    format_request_origin(request.scope), response.status_code,
                    dict(response.headers), response.body.decode('utf-8'),
                )
            response.headers['Cache-Control'] = 'no-store'
            return response

        return handler
