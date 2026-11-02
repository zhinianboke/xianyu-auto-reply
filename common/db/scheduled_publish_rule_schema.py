"""
商品定时发布相关表的幂等启动自检。

功能：
1. 创建并补齐定时发布规则表；
2. 创建并补齐定时发布记录表；
3. 创建并补齐定时发布触发记录表。
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import text


TABLE_DDLS = {
    "xy_scheduled_publish_rules": """
        CREATE TABLE IF NOT EXISTS xy_scheduled_publish_rules (
            id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '规则ID',
            owner_id BIGINT NOT NULL COMMENT '所属用户ID',
            rule_name VARCHAR(120) NOT NULL COMMENT '规则名称',
            account_ids JSON NOT NULL COMMENT '闲鱼账号ID列表',
            material_ids JSON NOT NULL COMMENT '商品素材ID列表',
            trigger_start_time TIME NOT NULL COMMENT '每日触发开始时间',
            trigger_end_time TIME NOT NULL COMMENT '每日触发结束时间',
            interval_min_minutes INT NOT NULL COMMENT '随机间隔最小分钟数',
            interval_max_minutes INT NOT NULL COMMENT '随机间隔最大分钟数',
            is_enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
            is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除（软删除）',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间（北京时间）',
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（北京时间）',
            INDEX idx_spr_owner_created (owner_id, created_at),
            INDEX idx_spr_owner_name (owner_id, rule_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品定时发布规则表'
    """,
    "xy_scheduled_publish_records": """
        CREATE TABLE IF NOT EXISTS xy_scheduled_publish_records (
            id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
            owner_id BIGINT NOT NULL COMMENT '所属用户ID',
            rule_id BIGINT NOT NULL COMMENT '定时发布规则ID',
            account_id VARCHAR(80) NOT NULL COMMENT '闲鱼账号ID',
            material_id BIGINT NULL COMMENT '商品素材ID，无可用素材时为空',
            publish_result VARCHAR(20) NOT NULL COMMENT '发布结果：success-成功，failure-失败',
            failure_reason TEXT NULL COMMENT '失败原因',
            publish_date DATE NOT NULL COMMENT '发布日期（北京时间）',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间（北京时间）',
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（北京时间）',
            INDEX idx_sprr_rule_account_date (rule_id, account_id, publish_date),
            INDEX idx_sprr_success_material (rule_id, account_id, publish_result, material_id),
            INDEX idx_sprr_owner_date (owner_id, publish_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='定时发布记录表'
    """,
    "xy_scheduled_publish_triggers": """
        CREATE TABLE IF NOT EXISTS xy_scheduled_publish_triggers (
            id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
            owner_id BIGINT NOT NULL COMMENT '所属用户ID',
            rule_id BIGINT NOT NULL COMMENT '定时发布规则ID',
            account_id VARCHAR(80) NOT NULL COMMENT '闲鱼账号ID',
            schedule_date DATE NOT NULL COMMENT '最近计划初始化日期（北京时间）',
            next_trigger_at DATETIME NOT NULL COMMENT '下次触发时间（北京时间）',
            is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除（软删除）',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间（北京时间）',
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（北京时间）',
            UNIQUE KEY uk_spt_owner_rule_account (owner_id, rule_id, account_id),
            INDEX idx_spt_next_trigger (next_trigger_at),
            INDEX idx_spt_owner (owner_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='定时发布触发记录表'
    """,
}

COLUMNS = {
    "xy_scheduled_publish_rules": {
        "id": "BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '规则ID'",
        "owner_id": "BIGINT NOT NULL DEFAULT 0 COMMENT '所属用户ID'",
        "rule_name": "VARCHAR(120) NOT NULL DEFAULT '' COMMENT '规则名称'",
        "account_ids": "JSON NULL COMMENT '闲鱼账号ID列表'",
        "material_ids": "JSON NULL COMMENT '商品素材ID列表'",
        "trigger_start_time": "TIME NULL COMMENT '每日触发开始时间'",
        "trigger_end_time": "TIME NULL COMMENT '每日触发结束时间'",
        "interval_min_minutes": "INT NOT NULL DEFAULT 60 COMMENT '随机间隔最小分钟数'",
        "interval_max_minutes": "INT NOT NULL DEFAULT 60 COMMENT '随机间隔最大分钟数'",
        "is_enabled": "TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用'",
        "is_deleted": "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除（软删除）'",
        "created_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间（北京时间）'",
        "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（北京时间）'",
    },
    "xy_scheduled_publish_records": {
        "id": "BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID'",
        "owner_id": "BIGINT NOT NULL DEFAULT 0 COMMENT '所属用户ID'",
        "rule_id": "BIGINT NOT NULL DEFAULT 0 COMMENT '定时发布规则ID'",
        "account_id": "VARCHAR(80) NOT NULL DEFAULT '' COMMENT '闲鱼账号ID'",
        "material_id": "BIGINT NULL COMMENT '商品素材ID，无可用素材时为空'",
        "publish_result": "VARCHAR(20) NOT NULL DEFAULT 'failure' COMMENT '发布结果：success-成功，failure-失败'",
        "failure_reason": "TEXT NULL COMMENT '失败原因'",
        "publish_date": "DATE NULL COMMENT '发布日期（北京时间）'",
        "created_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间（北京时间）'",
        "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（北京时间）'",
    },
    "xy_scheduled_publish_triggers": {
        "id": "BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID'",
        "owner_id": "BIGINT NOT NULL DEFAULT 0 COMMENT '所属用户ID'",
        "rule_id": "BIGINT NOT NULL DEFAULT 0 COMMENT '定时发布规则ID'",
        "account_id": "VARCHAR(80) NOT NULL DEFAULT '' COMMENT '闲鱼账号ID'",
        "schedule_date": "DATE NULL COMMENT '最近计划初始化日期（北京时间）'",
        "next_trigger_at": "DATETIME NULL COMMENT '下次触发时间（北京时间）'",
        "is_deleted": "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除（软删除）'",
        "created_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间（北京时间）'",
        "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（北京时间）'",
    },
}

INDEXES = {
    "xy_scheduled_publish_rules": {
        "idx_spr_owner_created": "INDEX `idx_spr_owner_created` (owner_id, created_at)",
        "idx_spr_owner_name": "INDEX `idx_spr_owner_name` (owner_id, rule_name)",
    },
    "xy_scheduled_publish_records": {
        "idx_sprr_rule_account_date": "INDEX `idx_sprr_rule_account_date` (rule_id, account_id, publish_date)",
        "idx_sprr_success_material": "INDEX `idx_sprr_success_material` (rule_id, account_id, publish_result, material_id)",
        "idx_sprr_owner_date": "INDEX `idx_sprr_owner_date` (owner_id, publish_date)",
    },
    "xy_scheduled_publish_triggers": {
        "uk_spt_owner_rule_account": "UNIQUE INDEX `uk_spt_owner_rule_account` (owner_id, rule_id, account_id)",
        "idx_spt_next_trigger": "INDEX `idx_spt_next_trigger` (next_trigger_at)",
        "idx_spt_owner": "INDEX `idx_spt_owner` (owner_id)",
    },
}


async def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """判断指定字段是否存在。"""
    result = await conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name "
            "AND COLUMN_NAME = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return bool(result.scalar())


async def _column_is_nullable(conn, table_name: str, column_name: str) -> bool:
    """判断指定字段是否允许为空。"""
    result = await conn.execute(
        text(
            "SELECT IS_NULLABLE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name "
            "AND COLUMN_NAME = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return str(result.scalar() or "").upper() == "YES"


async def _index_exists(conn, table_name: str, index_name: str) -> bool:
    """判断指定索引是否存在。"""
    result = await conn.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name "
            "AND INDEX_NAME = :index_name"
        ),
        {"table_name": table_name, "index_name": index_name},
    )
    return bool(result.scalar())


async def ensure_scheduled_publish_rule_schema(conn) -> None:
    """创建定时发布相关表，并幂等补齐缺失字段和索引。

    Args:
        conn: 数据库连接。
    Returns:
        无返回值。
    """
    for table_name, table_ddl in TABLE_DDLS.items():
        await conn.execute(text(table_ddl))
        for column_name, definition in COLUMNS[table_name].items():
            if not await _column_exists(conn, table_name, column_name):
                await conn.execute(
                    text(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {definition}")
                )
                logger.info("定时发布表补齐字段: table={}, column={}", table_name, column_name)

        if table_name == "xy_scheduled_publish_records" and not await _column_is_nullable(
            conn,
            table_name,
            "material_id",
        ):
            await conn.execute(
                text(
                    "ALTER TABLE `xy_scheduled_publish_records` "
                    "MODIFY COLUMN `material_id` BIGINT NULL "
                    "COMMENT '商品素材ID，无可用素材时为空'"
                )
            )
            logger.info("定时发布记录表素材字段已调整为允许为空")

        for index_name, definition in INDEXES[table_name].items():
            if not await _index_exists(conn, table_name, index_name):
                await conn.execute(text(f"ALTER TABLE `{table_name}` ADD {definition}"))
                logger.info("定时发布表补齐索引: table={}, index={}", table_name, index_name)

    logger.info("定时发布相关表结构自检完成")
