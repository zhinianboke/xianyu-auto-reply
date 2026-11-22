"""卡券安全相关结构变更：启动幂等增加软删除字段，不删除或修复历史业务数据。"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


_CARD_SOFT_DELETE_DDL = {
    "xy_cards": "ALTER TABLE xy_cards ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已软删除'",
    "xy_card_item_relations": "ALTER TABLE xy_card_item_relations ADD COLUMN is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已软删除'",
}


async def ensure_card_schema(conn: AsyncConnection) -> None:
    """在启动自检持锁的连接中补齐软删除字段；参数为DDL连接，失败记录堆栈并抛出。"""
    for table_name, ddl in _CARD_SOFT_DELETE_DDL.items():
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:table_name AND COLUMN_NAME=:column_name"
        ), {"table_name": table_name, "column_name": "is_deleted"})
        if result.scalar():
            logger.info("卡券软删除字段已存在: table={}", table_name)
            continue
        try:
            await conn.execute(text(ddl))
        except Exception:
            logger.exception("卡券软删除字段补齐失败，禁止继续启动: table={}", table_name)
            raise
        logger.info("卡券软删除字段补齐成功: table={}", table_name)
