"""
Scheduler服务核心启动逻辑

所有业务逻辑均在此文件中实现，main.py 仅作为最小入口桩。

功能：
1. 创建FastAPI应用
2. 设置日志输出
3. 挂载API路由
4. 启动定时任务
5. 统一错误处理
6. 数据库连接检查
"""
from __future__ import annotations

import asyncio
import faulthandler
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger

from app.core.config import get_settings
from common.utils.logging_utils import setup_logging
from common.utils.network_utils import resolve_listen_host

faulthandler.enable()

settings = get_settings()

# 配置日志（控制台 + 文件 + 第三方库拦截）
setup_logging(
    log_file=Path(__file__).parent / "logs" / "scheduler.log",
    log_level=settings.log_level,
    third_party_loggers=["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "apscheduler"],
)


async def check_database_connection():
    """
    检查数据库连接
    
    如果连接失败，记录错误并退出服务
    """
    try:
        from common.db.session import async_engine
        from sqlalchemy import text
        
        logger.info("正在检查数据库连接...")
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("数据库连接成功")
        return True
    except Exception as e:
        logger.error(f"数据库连接失败: {str(e)}")
        logger.error("请检查数据库配置和网络连接")
        logger.error(f"数据库地址: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info(f"{settings.project_name} 启动中...")
    logger.info(f"服务端口: {settings.service_port}")
    logger.info(f"数据库: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    
    # 检查数据库连接
    if not await check_database_connection():
        logger.error("数据库连接失败，服务退出")
        sys.exit(1)

    # 只读取 backend 已准备好的服务间 API 令牌，scheduler 不负责数据库初始化。
    try:
        from common.utils.internal_token_service import load_internal_api_token
        await load_internal_api_token(settings)
    except Exception as e:
        logger.error(f"内部 API 令牌加载失败: {e}")
        raise
    
    # 从数据库加载日志保留天数配置
    from common.utils.logging_utils import apply_db_log_retention, run_db_log_retention_sync
    await apply_db_log_retention()
    log_retention_sync_task = asyncio.create_task(run_db_log_retention_sync())
    
    # 启动定时任务
    from app.services.scheduler_service import get_scheduler_service
    scheduler = get_scheduler_service()
    scheduler.start()
    logger.info("定时任务管理器已启动")
    
    yield
    
    # 停止定时任务
    scheduler.stop()
    logger.info("定时任务管理器已停止")

    log_retention_sync_task.cancel()
    try:
        await log_retention_sync_task
    except asyncio.CancelledError:
        pass
    
    logger.info(f"{settings.project_name} 关闭中...")
    
    # 关闭HTTP客户端
    from app.core.http_client import close_http_client
    await close_http_client()
    logger.info("HTTP客户端已关闭")

    # 关闭复用的 goofish API 连接池
    from common.services.order_service import close_goofish_connector
    await close_goofish_connector()
    logger.info("goofish API 连接池已关闭")


# 创建FastAPI应用
app = FastAPI(
    title=settings.project_name,
    lifespan=lifespan,
)


# 全局异常处理器
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """将 HTTP 异常转换为项目统一的 HTTP 200 业务错误响应。"""
    logger.warning(
        "HTTP异常: {} - {}\n请求路径: {}\n请求方法: {}",
        exc.status_code,
        exc.detail,
        request.url.path,
        request.method,
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": False,
            "code": exc.status_code,
            "message": exc.detail,
            "data": None,
        },
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    """将请求参数校验错误转换为统一的 HTTP 200 业务响应。"""
    # 错误对象可能携带完整请求体，禁止把 Cookie/密码等敏感输入写入日志。
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
        status_code=200,
        content={
            "success": False,
            "code": 400,
            "message": "请求参数不正确",
            "data": None,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    全局异常处理器
    
    捕获所有未处理的异常,返回统一格式的错误响应
    """
    # 通过参数传递动态异常文本，避免异常 repr 中的 ``{}`` 被 Loguru 当作模板占位符。
    logger.opt(exception=exc).error(
        "全局异常捕获: {}: {}\n请求路径: {}\n请求方法: {}",
        type(exc).__name__,
        str(exc),
        request.url.path,
        request.method,
    )
    
    # 处理HTTPException
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=200,  # 统一返回200
            content={
                "success": False,
                "code": exc.status_code,
                "message": exc.detail,
                "data": None,
            },
        )
    
    # 其他异常
    return JSONResponse(
        status_code=200,  # 统一返回200
        content={
            "success": False,
            "code": 500,
            "message": f"服务器内部错误: {str(exc)}",
            "data": None,
        },
    )


# 挂载API路由
from app.api.routes import internal

app.include_router(internal.router)


@app.get("/health")
async def health_check():
    """
    健康检查接口
    
    Returns:
        服务健康状态
    """
    from common.db.session import async_engine
    from sqlalchemy import text
    
    # 检查数据库连接
    db_status = "unknown"
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception as e:
        logger.error(f"数据库连接检查失败: {str(e)}")
        db_status = "disconnected"
    
    return {
        "success": True,
        "code": 200,
        "message": "服务运行正常",
        "data": {
            "service": settings.project_name,
            "status": "running",
            "database": db_status,
        },
    }


def run_server():
    """启动HTTP服务（供 main.py 的 __main__ 块调用）"""
    import uvicorn

    # 解析监听地址：默认 :: 双栈，Windows 或 IPv6 不可用时自动回退到 0.0.0.0
    listen_host = resolve_listen_host(settings.host, settings.service_port)

    uvicorn.run(
        "main:app",
        host=listen_host,
        port=settings.service_port,
        reload=False,
        log_level=settings.log_level.lower(),
        # 保留公共日志工具配置，确保 Uvicorn 日志也进入普通日志和 error.log。
        log_config=None,
    )
