"""通用展示入口模板表的幂等建表。"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import text

DISPLAY_LINK_TABLE_DDL = """
    CREATE TABLE IF NOT EXISTS xy_display_link_templates (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        name VARCHAR(255) NOT NULL,
        type VARCHAR(16) NOT NULL,
        url VARCHAR(512) NULL,
        note VARCHAR(255) NULL,
        title VARCHAR(255) NULL,
        content TEXT NULL,
        is_default TINYINT(1) NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_dlt_user_default (user_id, is_default)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


async def ensure_display_link_schema(conn) -> None:
    """创建通用展示入口模板表（幂等，可重复执行）。"""
    await conn.execute(text(DISPLAY_LINK_TABLE_DDL))
    logger.info("通用展示入口模板表已就绪: xy_display_link_templates")
