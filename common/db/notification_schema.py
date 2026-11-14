"""
通知模块数据库结构自检。

功能：
1. 幂等补齐通知类型字段与软删除字段
2. 迁移失败时明确阻止服务带病启动
3. 仅新增字段并保留全部历史通知数据
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.exc import DBAPIError


NOTIFICATION_COLUMNS = (
    (
        "xy_notification_channels",
        "is_deleted",
        "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否删除：0-正常，1-已删除'",
    ),
    (
        "xy_message_notifications",
        "notify_types",
        "VARCHAR(64) NOT NULL DEFAULT 'chat,delivery,account' COMMENT '订阅的通知类型，逗号分隔'",
    ),
    (
        "xy_message_notifications",
        "is_deleted",
        "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否删除：0-正常，1-已删除'",
    ),
)

NOTIFICATION_INDEXES = (
    (
        "xy_message_notifications",
        "idx_msg_notify_owner_account_channel_deleted",
        "(`owner_id`, `account_pk`, `channel_id`, `is_deleted`, `enabled`, `id`)",
    ),
)


async def ensure_notification_schema(conn: AsyncConnection) -> None:
    """幂等补齐通知模块关键字段，失败时向启动入口抛出异常。

    Args:
        conn: 数据库初始化入口提供的异步连接。
    Returns:
        无返回值。
    """
    missing_tables = {
        table_name
        for table_name, _, _ in NOTIFICATION_COLUMNS
        if not await conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name"
            ),
            {"table_name": table_name},
        )
    }
    if missing_tables:
        raise RuntimeError(f"通知模块关键表缺失：{', '.join(sorted(missing_tables))}")

    for table_name, column_name, definition in NOTIFICATION_COLUMNS:
        exists = await conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = :table_name AND COLUMN_NAME = :column_name"
            ),
            {"table_name": table_name, "column_name": column_name},
        )
        if not exists:
            # 表名、字段名和定义均为本模块固定常量，不接收业务输入。
            try:
                await conn.execute(text(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {definition}"))
            except DBAPIError as error:
                # 其他服务可能在检查后完成相同DDL；只容忍明确的“字段已存在”，随后复核。
                if not error.orig.args or error.orig.args[0] != 1060:
                    raise
            logger.info("通知模块字段已补齐：{}.{}", table_name, column_name)

        verified = await conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = :table_name AND COLUMN_NAME = :column_name"
            ),
            {"table_name": table_name, "column_name": column_name},
        )
        if not verified:
            raise RuntimeError(f"通知模块关键字段缺失：{table_name}.{column_name}")

    for table_name, index_name, columns in NOTIFICATION_INDEXES:
        exists = await conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = :table_name AND INDEX_NAME = :index_name"
            ),
            {"table_name": table_name, "index_name": index_name},
        )
        if not exists:
            try:
                await conn.execute(text(f"ALTER TABLE `{table_name}` ADD INDEX `{index_name}` {columns}"))
            except DBAPIError as error:
                if not error.orig.args or error.orig.args[0] != 1061:
                    raise
            logger.info("通知模块索引已补齐：{}.{}", table_name, index_name)

        verified = await conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = :table_name AND INDEX_NAME = :index_name"
            ),
            {"table_name": table_name, "index_name": index_name},
        )
        if not verified:
            raise RuntimeError(f"通知模块关键索引缺失：{table_name}.{index_name}")

    logger.info("通知模块数据库结构自检完成，历史数据保持不变")


__all__ = ["ensure_notification_schema"]
