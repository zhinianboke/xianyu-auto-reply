"""
WebSocket服务统一错误处理

功能：
1. 统一错误响应格式
2. 全局异常捕获
3. 错误日志记录
"""
from __future__ import annotations

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    全局异常处理器
    
    捕获所有未处理的异常，返回统一格式的错误响应
    
    Args:
        request: 请求对象
        exc: 异常对象
        
    Returns:
        JSON响应
    """
    # 通过参数传递动态异常文本，避免异常 repr 中的 ``{}`` 被 Loguru 当作模板占位符。
    logger.opt(exception=exc).error(
        "全局异常捕获: {}: {}\n请求路径: {}\n请求方法: {}",
        type(exc).__name__,
        str(exc),
        request.url.path,
        request.method,
    )
    
    # 返回统一格式的错误响应
    return JSONResponse(
        status_code=status.HTTP_200_OK,  # 统一返回200
        content={
            "success": False,
            "code": 500,
            "message": f"服务器内部错误: {str(exc)}",
            "data": None,
        },
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    HTTP异常处理器
    
    处理FastAPI的HTTPException
    
    Args:
        request: 请求对象
        exc: HTTPException对象
        
    Returns:
        JSON响应
    """
    if isinstance(exc, HTTPException):
        # 通过参数传递动态异常文本，避免异常详情中的 ``{}`` 被 Loguru 当作模板占位符。
        logger.warning(
            "HTTP异常: {} - {}\n请求路径: {}\n请求方法: {}",
            exc.status_code,
            exc.detail,
            request.url.path,
            request.method,
        )
        
        # 返回统一格式的错误响应
        return JSONResponse(
            status_code=status.HTTP_200_OK,  # 统一返回200
            content={
                "success": False,
                "code": exc.status_code,
                "message": exc.detail,
                "data": None,
            },
        )
    
    # 其他异常交给全局异常处理器
    return await global_exception_handler(request, exc)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """将请求参数校验错误转换为统一的 HTTP 200 业务响应。"""
    # Pydantic 错误对象可能包含完整请求体，不能直接写入日志以免泄露 Cookie 等敏感数据。
    error_fields = [
        {
            "loc": [str(part) for part in error.get("loc", ())],
            "type": str(error.get("type", "unknown")),
        }
        for error in exc.errors()
    ]
    logger.warning(
        "请求参数校验失败: fields={}\n请求路径: {}\n请求方法: {}",
        error_fields,
        request.url.path,
        request.method,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": False,
            "code": 400,
            "message": "请求参数不正确",
            "data": None,
        },
    )


def setup_error_handlers(app):
    """
    设置错误处理器
    
    Args:
        app: FastAPI应用实例
    """
    # 注册HTTP异常处理器
    app.add_exception_handler(HTTPException, http_exception_handler)

    # 注册请求体/查询参数校验异常处理器
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    # 注册全局异常处理器
    app.add_exception_handler(Exception, global_exception_handler)
    
    logger.info("错误处理器已注册")
