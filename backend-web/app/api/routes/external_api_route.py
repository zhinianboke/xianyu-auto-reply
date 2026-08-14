"""
公开接口路由公共处理。

功能：
1. 将公开接口的请求参数校验异常统一转换为 HTTP 200 业务响应。
2. 避免外部调用方因 FastAPI 默认 422 响应而出现不同的错误处理分支。
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


class ExternalApiRoute(APIRoute):
    """公开接口统一路由，保证请求参数错误也使用业务响应格式。"""

    def get_route_handler(self) -> Any:
        """包装默认处理器并转换请求参数校验错误。"""
        original_handler = super().get_route_handler()

        async def validation_handler(request: Request) -> JSONResponse:
            """将 FastAPI 默认 422 转为公开接口统一业务错误。"""
            try:
                return await original_handler(request)
            except RequestValidationError as exc:
                errors = exc.errors()
                first_error = errors[0] if errors else {}
                location = first_error.get("loc") if isinstance(first_error, dict) else []
                last_location = location[-1] if isinstance(location, (list, tuple)) and location else None
                message = (
                    f"请求参数{last_location}不正确"
                    if isinstance(last_location, str)
                    else "请求体格式不正确"
                )
                return JSONResponse(
                    status_code=200,
                    content={
                        "success": False,
                        "code": 40008,
                        "message": message,
                        "data": None,
                    },
                )

        return validation_handler


__all__ = ["ExternalApiRoute"]
