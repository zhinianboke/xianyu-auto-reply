"""
WebSocket服务核心启动逻辑

main.py 仅作为最小入口桩；此文件装配应用，账号调度与健康探测由服务模块实现。

功能：
1. 创建FastAPI应用
2. 配置CORS
3. 设置日志输出
4. 挂载API路由
5. 统一错误处理
6. 数据库连接检查
7. 管理账号后台启动与退出清理
"""
from __future__ import annotations

import asyncio
import faulthandler
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import get_settings
from app.core.error_handlers import setup_error_handlers
from app.api.routes import cookies_refresh, internal, password_login
from app.services.account_startup import AccountStartup
from app.services.service_health import check_database_connection
from app.services.xianyu.cookie_manager import get_manager
from common.db.redis_client import close_redis_client, initialize_redis_client
from common.services.cookie_renew_browser_service import enable_local_browser_renew
from common.services.order_service import close_goofish_connector
from common.services.captcha.slider_mode import refresh_slider_mode_from_database
from common.services.risk_control_log_cleanup_service import (
    fail_processing_risk_control_logs_on_restart,
)
from common.utils.internal_token_service import load_internal_api_token
from common.utils.logging_utils import (
    apply_db_log_retention, run_db_log_retention_sync, setup_logging,
)
from common.utils.network_utils import resolve_listen_host

faulthandler.enable()

settings = get_settings()

# 配置日志（控制台 + 文件 + 第三方库拦截）
setup_logging(
    log_file=Path(__file__).parent / "logs" / "websocket.log",
    log_level=settings.log_level,
    third_party_loggers=["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "websockets", "httpx", "httpcore"],
)


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
    logger.info("数据库连接成功")

    # 初始化 Redis 健康连接池；失败时按指数退避重试，最终失败则停止启动。
    try:
        await initialize_redis_client()
    except Exception:
        logger.exception("Redis连接初始化失败，服务退出")
        raise

    # 只读取 backend 已准备好的服务间 API 令牌，WebSocket 不负责数据库初始化。
    try:
        await load_internal_api_token(settings)
    except Exception as e:
        logger.error(f"内部 API 令牌加载失败: {e}")
        raise

    cleanup_result = await fail_processing_risk_control_logs_on_restart()
    if not cleanup_result.success:
        logger.error(cleanup_result.message)
        raise RuntimeError(cleanup_result.message)
    if cleanup_result.updated_count:
        logger.warning(cleanup_result.message)
    else:
        logger.info(cleanup_result.message)

    await refresh_slider_mode_from_database()
    
    # 从数据库加载日志保留天数配置
    await apply_db_log_retention()
    log_retention_sync_task = asyncio.create_task(run_db_log_retention_sync())
    
    # 初始化CookieManager
    cookie_manager = get_manager(asyncio.get_running_loop())
    logger.info("CookieManager已初始化")
    startup = AccountStartup(cookie_manager, settings.auto_start_websocket)
    app.state.account_startup = startup
    try:
        async with startup.run():
            logger.info(f"{settings.project_name} HTTP服务已就绪")
            yield
    finally:
        logger.info(f"{settings.project_name} 关闭中...")
        log_retention_sync_task.cancel()
        try:
            await log_retention_sync_task
        except asyncio.CancelledError:
            logger.info("日志保留配置同步任务已停止")
        await close_goofish_connector()
        logger.info("goofish API 连接池已关闭")
        # 先释放Redis客户端，再断开全局连接池。
        try:
            await close_redis_client()
        except Exception:
            logger.exception("关闭Redis连接失败")


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
setup_error_handlers(app)

# 挂载API路由
app.include_router(internal.router)
app.include_router(cookies_refresh.router)
app.include_router(password_login.router)

# 开启本进程内浏览器续期执行：所有浏览器续期（含 scheduler / backend-web 的 HTTP 委托）
# 统一收敛到 WebSocket 进程，与滑块验证同进程串行，复用持久化目录与账号级互斥锁。
enable_local_browser_renew()


@app.get("/health")
async def health_check():
    """
    健康检查接口
    
    Returns:
        服务健康状态
    """
    response = await health_ping()
    connected = await check_database_connection()
    response["data"]["database"] = "connected" if connected else "disconnected"
    if not connected:
        response["message"] = "HTTP服务已启动，数据库连接检查失败"
    return response


@app.get("/health/ping")
async def health_ping():
    """返回 HTTP 存活状态和账号调度进度，不访问数据库或等待账号连接。"""
    return {
        "success": True,
        "code": 200,
        "message": "HTTP服务已启动",
        "data": {
            "service": settings.project_name,
            "status": "running",
            "account_startup": app.state.account_startup.get_status(),
        },
    }


def run_server():
    """启动HTTP服务（供 main.py 的 __main__ 块调用）"""
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
