"""WebSocket 服务数据库健康探测，统一限制数据库检查等待时间。"""
from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import text

from common.db.session import async_engine

DATABASE_PROBE_TIMEOUT = 5.0


async def check_database_connection() -> bool:
    """在五秒内检查共享数据库连接，失败时记录完整堆栈并返回 False。"""
    try:
        async with asyncio.timeout(DATABASE_PROBE_TIMEOUT):
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("WebSocket服务数据库连接检查失败")
        return False
