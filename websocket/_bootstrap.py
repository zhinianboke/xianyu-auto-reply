"""
WebSocket服务核心启动逻辑

所有业务逻辑均在此文件中实现，main.py 仅作为最小入口桩。

功能：
1. 创建FastAPI应用
2. 配置CORS
3. 设置日志输出
4. 挂载API路由
5. 统一错误处理
6. 数据库连接检查
"""
from __future__ import annotations

import asyncio
import faulthandler
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import get_settings
from common.utils.logging_utils import setup_logging
from common.utils.network_utils import resolve_listen_host
from common.services.captcha.slider_mode import refresh_slider_mode_from_database

faulthandler.enable()

settings = get_settings()

# 配置日志（控制台 + 文件 + 第三方库拦截）
setup_logging(
    log_file=Path(__file__).parent / "logs" / "websocket.log",
    log_level=settings.log_level,
    third_party_loggers=["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "websockets", "httpx", "httpcore"],
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

    await refresh_slider_mode_from_database()
    
    # 从数据库加载日志保留天数配置
    from common.utils.logging_utils import apply_db_log_retention, run_db_log_retention_sync
    await apply_db_log_retention()
    log_retention_sync_task = asyncio.create_task(run_db_log_retention_sync())
    
    # 初始化CookieManager
    from app.services.xianyu.cookie_manager import get_manager
    cookie_manager = get_manager()
    logger.info("CookieManager已初始化")
    
    # 启动CookieManager(加载启用的账号)，可通过配置禁用
    if settings.auto_start_websocket:
        try:
            await cookie_manager.start()
            logger.info("CookieManager已启动,账号任务已加载")
        except Exception as e:
            logger.error(f"CookieManager启动失败: {e}")
    else:
        logger.info("已禁用自动启动WebSocket连接（AUTO_START_WEBSOCKET=false）")
    
    yield
    
    logger.info(f"{settings.project_name} 关闭中...")
    
    # 停止CookieManager
    try:
        await cookie_manager.stop()
        logger.info("CookieManager已停止")
    except Exception as e:
        logger.error(f"CookieManager停止失败: {e}")

    log_retention_sync_task.cancel()
    try:
        await log_retention_sync_task
    except asyncio.CancelledError:
        pass

    # 关闭复用的 goofish API 连接池
    from common.services.order_service import close_goofish_connector
    await close_goofish_connector()
    logger.info("goofish API 连接池已关闭")


# 创建FastAPI应用
app = FastAPI(
    title=settings.project_name,
    lifespan=lifespan,
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 设置错误处理器
from app.core.error_handlers import setup_error_handlers
setup_error_handlers(app)

# 挂载API路由
from app.api.routes import cookies_refresh, internal, password_login

app.include_router(internal.router)
app.include_router(cookies_refresh.router)
app.include_router(password_login.router)

# 开启本进程内浏览器续期执行：所有浏览器续期（含 scheduler / backend-web 的 HTTP 委托）
# 统一收敛到 WebSocket 进程，与滑块验证同进程串行，复用持久化目录与账号级互斥锁。
from common.services.cookie_renew_browser_service import enable_local_browser_renew

enable_local_browser_renew()


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
    )
