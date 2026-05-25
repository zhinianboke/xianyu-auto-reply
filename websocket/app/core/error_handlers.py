"""
WebSocket服务统一错误处理

功能：
1. 统一错误响应格式
2. 全局异常捕获
3. 错误日志记录
"""
from __future__ import annotations

from fastapi import Request, status
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
    # 记录错误日志
    logger.error(
        f"全局异常捕获: {type(exc).__name__}: {str(exc)}\n"
        f"请求路径: {request.url.path}\n"
        f"请求方法: {request.method}"
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
    from fastapi import HTTPException
    
    if isinstance(exc, HTTPException):
        # 记录错误日志
        logger.warning(
            f"HTTP异常: {exc.status_code} - {exc.detail}\n"
            f"请求路径: {request.url.path}\n"
            f"请求方法: {request.method}"
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


def setup_error_handlers(app):
    """
    设置错误处理器
    
    Args:
        app: FastAPI应用实例
    """
    from fastapi import HTTPException
    
    # 注册HTTP异常处理器
    app.add_exception_handler(HTTPException, http_exception_handler)
    
    # 注册全局异常处理器
    app.add_exception_handler(Exception, global_exception_handler)
    
    logger.info("错误处理器已注册")
