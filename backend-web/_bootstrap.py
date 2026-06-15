"""
Backend-Web服务核心启动逻辑

所有业务逻辑均在此文件中实现，main.py 仅作为最小入口桩。

功能：
1. 创建FastAPI应用
2. 配置CORS
3. 挂载静态文件目录
4. 设置日志输出（使用loguru）
5. 挂载API路由
6. 统一错误处理
7. 数据库连接检查
"""
from __future__ import annotations

import asyncio
import faulthandler
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.core.config import get_settings
from common.utils.logging_utils import setup_logging
from common.utils.network_utils import resolve_listen_host

faulthandler.enable()

settings = get_settings()

# 配置日志（控制台 + 文件 + 第三方库拦截）
setup_logging(
    log_file=Path(__file__).parent / "logs" / "backend-web.log",
    log_level=settings.log_level,
    third_party_loggers=["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "httpx", "httpcore", "sqlalchemy"],
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
    
    # 初始化数据库（创建表、默认数据等）
    try:
        from common.db.init_database import init_database
        await init_database()
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
    
    # 自检 JWT 密钥：弱/默认值时自动生成强随机密钥并持久化（源码启动兜底）
    try:
        from app.services.jwt_secret_service import ensure_jwt_secret_key
        await ensure_jwt_secret_key(settings)
    except Exception as e:
        logger.error(f"JWT 密钥自检失败: {e}")
    
    # 从数据库加载日志保留天数配置
    from common.utils.logging_utils import apply_db_log_retention, run_db_log_retention_sync
    await apply_db_log_retention()
    log_retention_sync_task = asyncio.create_task(run_db_log_retention_sync())
    
    # 确保上传目录存在
    static_path = Path(settings.static_dir)
    upload_dirs = [
        static_path / "uploads",
        static_path / "uploads" / "face",
        static_path / "uploads" / "default_reply",
        static_path / "uploads" / "item_reply",
        static_path / "uploads" / "keywords",
        static_path / "uploads" / "confirm_receipt",
        static_path / "uploads" / "images",
        static_path / "uploads" / "files",
    ]
    for upload_dir in upload_dirs:
        upload_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"静态文件目录: {static_path.absolute()}")
    logger.info("所有上传子目录已创建")
    
    # 启动 Goofish 定时采集任务（可通过配置禁用）
    if settings.auto_start_crawl_jobs:
        try:
            await start_goofish_crawl_jobs()
        except Exception as e:
            logger.error(f"启动 Goofish 定时采集任务失败: {e}")
    else:
        logger.info("已禁用自动启动Goofish定时采集任务（AUTO_START_CRAWL_JOBS=false）")
    
    yield
    
    logger.info(f"{settings.project_name} 关闭中...")
    
    # 停止所有在线聊天IM会话
    try:
        from app.services.chat_new import get_im_session_manager
        chat_manager = get_im_session_manager()
        await chat_manager.disconnect_all()
        logger.info("所有在线聊天IM会话已停止")
    except Exception as e:
        logger.error(f"停止在线聊天IM会话失败: {e}")
    
    # 停止 Goofish 定时采集任务
    try:
        await stop_goofish_crawl_jobs()
    except Exception as e:
        logger.error(f"停止 Goofish 定时采集任务失败: {e}")
    
    # 关闭HTTP客户端
    from app.core.http_client import close_http_client
    await close_http_client()
    logger.info("HTTP客户端已关闭")

    # 关闭复用的 goofish API 连接池
    from common.services.order_service import close_goofish_connector
    await close_goofish_connector()
    logger.info("goofish API 连接池已关闭")

    log_retention_sync_task.cancel()
    try:
        await log_retention_sync_task
    except asyncio.CancelledError:
        pass


async def start_goofish_crawl_jobs():
    """启动所有启用的 Goofish 定时采集任务"""
    from app.services.goofish_crawler import get_goofish_crawl_manager
    from common.db.session import async_session_maker
    from sqlalchemy import select
    from common.models.goofish_crawl_job import GoofishCrawlJob
    
    logger.info("开始加载 Goofish 定时采集任务...")
    
    manager = get_goofish_crawl_manager()
    
    async with async_session_maker() as session:
        # 查询所有启用的任务
        result = await session.execute(
            select(GoofishCrawlJob).where(GoofishCrawlJob.enabled == True)
        )
        jobs = result.scalars().all()
        
        started_count = 0
        for job in jobs:
            try:
                manager.start_job(job_id=job.id)
                started_count += 1
                logger.info(f"已启动 Goofish 采集任务: job_id={job.id}, keyword={job.keyword}")
            except Exception as e:
                logger.error(f"启动 Goofish 采集任务失败: job_id={job.id}, error={e}")
        
        logger.info(f"Goofish 定时采集任务启动完成，共启动 {started_count} 个任务")


async def stop_goofish_crawl_jobs():
    """停止所有 Goofish 定时采集任务"""
    from app.services.goofish_crawler import get_goofish_crawl_manager
    
    try:
        manager = get_goofish_crawl_manager()
        await manager.stop_all()
        logger.info("所有 Goofish 定时采集任务已停止")
    except Exception as e:
        logger.error(f"停止 Goofish 定时采集任务失败: {e}")


# 创建FastAPI应用
app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    lifespan=lifespan,
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
static_path = Path(settings.static_dir)
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
    logger.info(f"静态文件路径已挂载: /static -> {static_path.absolute()}")


# 挂载API路由
from app.api import api_router

app.include_router(api_router, prefix="/api/v1")


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
            "version": settings.version,
            "status": "running",
            "database": db_status,
        },
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    全局异常处理器
    
    捕获所有未处理的异常,返回统一格式的错误响应
    """
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    
    # 记录错误日志
    # 注意：loguru 默认对 message 调用 str.format(*args, **kwargs)。
    # 如果用 f-string 把 str(exc) 拼进 message，且 str(exc) 中含有 '{xxx}' 字面量
    # （例如 ResponseValidationError 的报错里就含有 dict repr），
    # loguru 会把这些 '{xxx}' 误认为是 format 占位符，进而抛 KeyError，
    # 让全局异常处理器自身崩溃，掩盖原始错误。
    # 解决：把动态值通过位置参数传入，message 里用 '{}' 占位（args 内的 '{' 不会被二次 format）。
    # 同时用 logger.opt(exception=exc) 让 loguru 自动附带 traceback，替代旧的 exc_info=True。
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
    )
