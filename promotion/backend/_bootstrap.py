"""
推广返佣系统 - 后端服务核心启动逻辑

所有业务逻辑均在此文件中实现，main.py 仅作为最小入口桩。

功能：
1. FastAPI应用创建和配置
2. 数据库连接检查
3. CORS中间件配置
4. API路由注册
5. 静态文件服务
6. 全局异常处理
7. 定时任务注册
"""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger


def _setup_windows_event_loop_policy() -> None:
    """Windows环境下切换为ProactorEventLoopPolicy"""
    if sys.platform != "win32" or not hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        return
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        logger.info("Windows事件循环已切换为ProactorEventLoopPolicy")
    except Exception as exc:
        logger.warning(f"设置Windows事件循环策略失败: {exc}")


_setup_windows_event_loop_policy()

from app.core.config import get_settings
from app.services.database_check_service import check_database_connection, init_fy_tables

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("=" * 60)
    logger.info(f"推广返佣系统后端服务启动中...")
    logger.info(f"服务端口: {settings.service_port}")
    logger.info(f"环境: {settings.environment}")
    logger.info("=" * 60)

    # 检查数据库连接
    db_ok = await check_database_connection()
    if db_ok:
        logger.info("数据库连接正常")
        # 自检表结构，自动创建缺失的表
        await init_fy_tables()
        # 从数据库加载日志保留天数配置
        from common.utils.logging_utils import apply_db_log_retention, run_db_log_retention_sync
        await apply_db_log_retention()
        log_retention_sync_task = asyncio.create_task(run_db_log_retention_sync())
    else:
        logger.warning("数据库连接失败，部分功能可能不可用")
        log_retention_sync_task = None

    # 启动选品规则定时任务
    from app.services.product_rule_scheduler import run_product_rule_scheduler
    scheduler_task = asyncio.create_task(run_product_rule_scheduler())
    logger.info("选品规则定时任务已注册")

    # 启动发布规则定时任务
    from app.services.publish_rule_scheduler import run_publish_rule_scheduler
    publish_task = asyncio.create_task(run_publish_rule_scheduler())
    logger.info("发布规则定时任务已注册")

    # 启动发布卡券补偿定时任务
    from app.services.publish_coupon_card_scheduler import run_publish_coupon_card_scheduler
    publish_coupon_card_task = asyncio.create_task(run_publish_coupon_card_scheduler())
    logger.info("发布卡券补偿定时任务已注册")

    # 启动发布后商品ID回写补偿定时任务
    from app.services.published_item_id_repair_scheduler import run_published_item_id_repair_scheduler
    published_item_id_repair_task = asyncio.create_task(run_published_item_id_repair_scheduler())
    logger.info("发布后商品ID回写补偿定时任务已注册")

    # 启动素材短连接回填补偿定时任务
    from app.services.material_short_url_repair_scheduler import run_material_short_url_repair_scheduler
    material_short_url_repair_task = asyncio.create_task(run_material_short_url_repair_scheduler())
    logger.info("素材短连接回填补偿定时任务已注册")

    # 启动删除规则定时任务
    from app.services.delete_rule_scheduler import run_delete_rule_scheduler
    delete_rule_task = asyncio.create_task(run_delete_rule_scheduler())
    logger.info("删除规则定时任务已注册")

    yield

    # 停止定时任务
    scheduler_task.cancel()
    publish_task.cancel()
    publish_coupon_card_task.cancel()
    published_item_id_repair_task.cancel()
    material_short_url_repair_task.cancel()
    delete_rule_task.cancel()
    if log_retention_sync_task is not None:
        log_retention_sync_task.cancel()
        try:
            await log_retention_sync_task
        except asyncio.CancelledError:
            pass
    logger.info("推广返佣系统后端服务已停止")


# 创建FastAPI应用
app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    lifespan=lifespan,
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=200,
        content={"success": False, "message": f"服务器内部错误: {str(exc)}"},
    )


# 注册API路由
from app.api import api_router
app.include_router(api_router, prefix=settings.api_v1_prefix)


# 配置日志（使用公共日志工具，统一日志格式和保留策略）
from common.utils.logging_utils import setup_logging
setup_logging(
    log_file=Path(__file__).parent / "logs" / "promotion.log",
    log_level=settings.log_level,
    third_party_loggers=["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"],
)


def run_server():
    """启动HTTP服务（供 main.py 的 __main__ 块调用）"""
    reload_enabled = True
    if sys.platform == "win32":
        reload_enabled = False
        logger.warning("Windows环境已自动关闭reload，避免Playwright因SelectorEventLoop无法启动浏览器子进程")
    uvicorn.run(
        "main:app",
        host=settings.host,  # 默认 "::" 双栈监听，可通过 HOST 环境变量覆盖
        port=settings.service_port,
        reload=reload_enabled,
    )
