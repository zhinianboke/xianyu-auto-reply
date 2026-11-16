"""认证异常后的数据库会话恢复，避免回滚失败阻断审计或复用失效连接。"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession


async def rollback_session(session: AsyncSession, *, operation: str) -> bool:
    """回滚失败事务，必要时丢弃连接；返回会话是否可安全用于后续独立事务。

    Args:
        session: 当前请求的数据库会话。
        operation: 发生异常的操作名称，用于记录恢复失败的上下文。
    Returns:
        恢复成功返回 True；回滚和连接失效处理均失败时返回 False。
    """
    try:
        await session.rollback()
        return True
    except Exception as exc:
        logger.opt(exception=exc).error("数据库回滚失败，丢弃失效连接：operation={}", operation)
    try:
        await session.invalidate()
        return True
    except Exception as exc:
        logger.opt(exception=exc).error("数据库会话恢复失败：operation={}", operation)
        return False
