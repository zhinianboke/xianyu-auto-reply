"""
推广返佣系统 - 数据库检测服务

功能：
1. 检查数据库连接是否正常
2. 服务启动时自动创建缺失的 fy_ 表
3. 服务启动时自动补建 fy_ 表缺失字段
"""
from __future__ import annotations

from collections.abc import Iterable

from loguru import logger
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

from common.db.base_class import Base
from common.db.session import async_engine, async_session_maker
from common.models.fy_material import PUBLISH_STATUS_FAILED, PUBLISH_STATUS_PUBLISHED, PUBLISH_STATUS_UNPUBLISHED


def _register_fy_models() -> None:
    """注册 fy_ 开头模型，确保 Base.metadata 中已加载相关表定义。"""
    from common.models.fy_account import FYAccount  # noqa: F401
    from common.models.fy_material import FYMaterial  # noqa: F401
    from common.models.fy_product_rule import FYProductRule  # noqa: F401
    from common.models.fy_publish_rule import FYPublishRule  # noqa: F401
    from common.models.fy_delete_rule import FYDeleteRule  # noqa: F401


async def check_database_connection() -> bool:
    """检查数据库连接是否正常。"""
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"数据库连接检查失败: {e}")
        return False


async def init_fy_tables() -> None:
    """自检返佣系统数据库表，自动创建缺失表并补建缺失字段。"""
    try:
        _register_fy_models()
        async with async_engine.connect() as conn:
            existing_tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
            fy_tables = {
                table_name: table
                for table_name, table in Base.metadata.tables.items()
                if table_name.startswith("fy_")
            }
            tables_to_create = [table for table_name, table in fy_tables.items() if table_name not in existing_tables]
            for table_name in fy_tables:
                if table_name not in existing_tables:
                    logger.info(f"检测到缺失表: {table_name}，将自动创建")
            if tables_to_create:
                await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables_to_create))
                await conn.commit()
                logger.info(f"成功创建 {len(tables_to_create)} 个表")
            else:
                logger.info("所有fy_表已存在，无需创建")
            migration_flags = await _check_and_add_columns(conn, existing_tables)
        if migration_flags["need_rule_account_sync"]:
            await _sync_rule_account_dimensions()
    except Exception as e:
        logger.error(f"数据库表自检失败: {e}")


async def _check_and_add_columns(conn: AsyncConnection, existing_tables: list[str]) -> dict[str, bool]:
    """检查 fy_ 相关表的缺失字段并自动补建。"""
    await _check_accounts_columns(conn, existing_tables)
    product_rule_account_added = await _check_product_rules_columns(conn, existing_tables)
    material_flags = await _check_materials_columns(conn, existing_tables)
    await _check_publish_rules_columns(conn, existing_tables)
    await _check_delete_rules_columns(conn, existing_tables)
    return {
        "need_rule_account_sync": product_rule_account_added or material_flags["account_id_added"],
    }


async def _get_table_columns(conn: AsyncConnection, table_name: str) -> list[str]:
    """获取指定表的现有字段列表。"""
    return await conn.run_sync(
        lambda sync_conn: [col["name"] for col in inspect(sync_conn).get_columns(table_name)]
    )


async def _get_table_indexes(conn: AsyncConnection, table_name: str) -> list[dict]:
    """获取指定表的现有索引列表。"""
    return await conn.run_sync(
        lambda sync_conn: inspect(sync_conn).get_indexes(table_name)
    )


async def _get_table_unique_constraints(conn: AsyncConnection, table_name: str) -> list[dict]:
    return await conn.run_sync(
        lambda sync_conn: inspect(sync_conn).get_unique_constraints(table_name)
    )


async def _ensure_index(conn: AsyncConnection, table_name: str, index_name: str, column_names: list[str], create_stmt: str) -> None:
    """确保指定表存在目标索引，若缺失则自动补建。"""
    indexes = await _get_table_indexes(conn, table_name)
    normalized_columns = tuple(column_names)
    for index in indexes:
        existing_name = str(index.get("name") or "").strip()
        existing_columns = tuple(index.get("column_names") or [])
        if existing_name == index_name or existing_columns == normalized_columns:
            return
    logger.info(f"检测到 {table_name} 缺失索引 {index_name}，将自动添加")
    await _apply_alter_statements(conn, table_name, [create_stmt])


async def _ensure_unique_constraint(
    conn: AsyncConnection,
    table_name: str,
    constraint_name: str,
    column_names: list[str],
    create_stmt: str,
) -> None:
    unique_constraints = await _get_table_unique_constraints(conn, table_name)
    normalized_columns = tuple(column_names)
    for constraint in unique_constraints:
        existing_name = str(constraint.get("name") or "").strip()
        existing_columns = tuple(constraint.get("column_names") or [])
        if existing_name == constraint_name or existing_columns == normalized_columns:
            return
    indexes = await _get_table_indexes(conn, table_name)
    for index in indexes:
        existing_name = str(index.get("name") or "").strip()
        existing_columns = tuple(index.get("column_names") or [])
        if existing_name == constraint_name or existing_columns == normalized_columns:
            if bool(index.get("unique")):
                return
    logger.info(f"检测到 {table_name} 缺失唯一约束 {constraint_name}，将自动添加")
    await _apply_alter_statements(conn, table_name, [create_stmt])


async def _apply_alter_statements(conn: AsyncConnection, table_name: str, alter_stmts: Iterable[str]) -> None:
    """按顺序执行字段补建 SQL，并在成功后统一提交。"""
    statements = [stmt for stmt in alter_stmts if stmt]
    for stmt in statements:
        await conn.execute(text(stmt))
    if statements:
        await conn.commit()
        logger.info(f"成功为 {table_name} 补建 {len(statements)} 个字段")


async def _check_accounts_columns(conn: AsyncConnection, existing_tables: list[str]) -> None:
    """检查 fy_accounts 表是否缺失返佣系统依赖字段。"""
    if "fy_accounts" not in existing_tables:
        return
    columns = await _get_table_columns(conn, "fy_accounts")
    alter_stmts = []
    if "app_key" not in columns:
        alter_stmts.append("ALTER TABLE fy_accounts ADD COLUMN app_key VARCHAR(80) DEFAULT NULL COMMENT '淘宝开放平台AppKey'")
        logger.info("检测到 fy_accounts 缺失字段 app_key，将自动添加")
    if "app_secret" not in columns:
        alter_stmts.append("ALTER TABLE fy_accounts ADD COLUMN app_secret VARCHAR(200) DEFAULT NULL COMMENT '淘宝开放平台AppSecret'")
        logger.info("检测到 fy_accounts 缺失字段 app_secret，将自动添加")
    if "adzone_id" not in columns:
        alter_stmts.append("ALTER TABLE fy_accounts ADD COLUMN adzone_id VARCHAR(80) DEFAULT NULL COMMENT '淘宝推广位ID'")
        logger.info("检测到 fy_accounts 缺失字段 adzone_id，将自动添加")
    await _apply_alter_statements(conn, "fy_accounts", alter_stmts)


async def _check_product_rules_columns(conn: AsyncConnection, existing_tables: list[str]) -> bool:
    """检查 fy_product_rules 表是否缺失选品规则运行字段。"""
    if "fy_product_rules" not in existing_tables:
        return False
    columns = await _get_table_columns(conn, "fy_product_rules")
    alter_stmts = []
    account_id_added = False
    total_selected_count_added = False
    if "last_run_date" not in columns:
        alter_stmts.append("ALTER TABLE fy_product_rules ADD COLUMN last_run_date DATE DEFAULT NULL COMMENT '最后执行日期'")
        logger.info("检测到 fy_product_rules 缺失字段 last_run_date，将自动添加")
    if "today_count" not in columns:
        alter_stmts.append("ALTER TABLE fy_product_rules ADD COLUMN today_count INT DEFAULT 0 COMMENT '今天已选品数量'")
        logger.info("检测到 fy_product_rules 缺失字段 today_count，将自动添加")
    if "total_selected_count" not in columns:
        alter_stmts.append("ALTER TABLE fy_product_rules ADD COLUMN total_selected_count INT DEFAULT 0 COMMENT '累计选品数量'")
        logger.info("检测到 fy_product_rules 缺失字段 total_selected_count，将自动添加")
        total_selected_count_added = True
    if "account_id" not in columns:
        alter_stmts.append("ALTER TABLE fy_product_rules ADD COLUMN account_id VARCHAR(80) DEFAULT NULL COMMENT '闲鱼账号ID（xy_accounts.account_id）'")
        logger.info("检测到 fy_product_rules 缺失字段 account_id，将自动添加")
        account_id_added = True
    await _apply_alter_statements(conn, "fy_product_rules", alter_stmts)
    await _ensure_index(
        conn,
        "fy_product_rules",
        "ix_fy_product_rules_account_id",
        ["account_id"],
        "CREATE INDEX ix_fy_product_rules_account_id ON fy_product_rules (account_id)",
    )
    if total_selected_count_added and "fy_materials" in existing_tables:
        await conn.execute(
            text(
                "UPDATE fy_product_rules "
                "SET total_selected_count = ("
                "SELECT COUNT(*) FROM fy_materials WHERE fy_materials.rule_id = fy_product_rules.id"
                ")"
            )
        )
        await conn.commit()
    return account_id_added


async def _check_materials_columns(conn: AsyncConnection, existing_tables: list[str]) -> dict[str, bool]:
    """检查 fy_materials 表是否缺失素材和发布相关字段。"""
    if "fy_materials" not in existing_tables:
        return {"account_id_added": False, "publish_status_added": False, "published_added": False}
    columns = await _get_table_columns(conn, "fy_materials")
    alter_stmts = []
    account_id_added = False
    publish_status_added = False
    published_added = False
    if "account_id" not in columns:
        alter_stmts.append("ALTER TABLE fy_materials ADD COLUMN account_id VARCHAR(80) DEFAULT NULL COMMENT '闲鱼账号ID（xy_accounts.account_id）'")
        logger.info("检测到 fy_materials 缺失字段 account_id，将自动添加")
        account_id_added = True
    if "stock" not in columns:
        alter_stmts.append("ALTER TABLE fy_materials ADD COLUMN stock INT NOT NULL DEFAULT 999 COMMENT '库存'")
        logger.info("检测到 fy_materials 缺失字段 stock，将自动添加")
    if "commission_amount" not in columns:
        alter_stmts.append("ALTER TABLE fy_materials ADD COLUMN commission_amount VARCHAR(20) DEFAULT NULL COMMENT '佣金金额'")
        logger.info("检测到 fy_materials 缺失字段 commission_amount，将自动添加")
    if "promotion_price" not in columns:
        alter_stmts.append("ALTER TABLE fy_materials ADD COLUMN promotion_price VARCHAR(20) DEFAULT NULL COMMENT '到手价'")
        logger.info("检测到 fy_materials 缺失字段 promotion_price，将自动添加")
    if "coupon_info" not in columns:
        alter_stmts.append("ALTER TABLE fy_materials ADD COLUMN coupon_info VARCHAR(255) DEFAULT NULL COMMENT '优惠券信息'")
        logger.info("检测到 fy_materials 缺失字段 coupon_info，将自动添加")
    if "short_url" not in columns:
        alter_stmts.append("ALTER TABLE fy_materials ADD COLUMN short_url VARCHAR(1000) DEFAULT NULL COMMENT '短连接'")
        logger.info("检测到 fy_materials 缺失字段 short_url，将自动添加")
    if "publish_status" not in columns:
        alter_stmts.append(
            "ALTER TABLE fy_materials ADD COLUMN publish_status VARCHAR(20) NOT NULL DEFAULT 'unpublished' COMMENT '发布状态'"
        )
        logger.info("检测到 fy_materials 缺失字段 publish_status，将自动添加")
        publish_status_added = True
    if "published" not in columns:
        alter_stmts.append("ALTER TABLE fy_materials ADD COLUMN published TINYINT(1) DEFAULT 0 COMMENT '是否已发布到闲鱼'")
        logger.info("检测到 fy_materials 缺失字段 published，将自动添加")
        published_added = True
    if "published_at" not in columns:
        alter_stmts.append("ALTER TABLE fy_materials ADD COLUMN published_at DATETIME DEFAULT NULL COMMENT '发布时间'")
        logger.info("检测到 fy_materials 缺失字段 published_at，将自动添加")
    if "published_item_id" not in columns:
        alter_stmts.append("ALTER TABLE fy_materials ADD COLUMN published_item_id VARCHAR(64) DEFAULT NULL COMMENT '发布后闲鱼商品ID'")
        logger.info("检测到 fy_materials 缺失字段 published_item_id，将自动添加")
    if "publish_random_str" not in columns:
        if "publish_trace_code" in columns:
            alter_stmts.append("ALTER TABLE fy_materials CHANGE COLUMN publish_trace_code publish_random_str VARCHAR(32) DEFAULT NULL COMMENT '发布随机字符'")
            logger.info("检测到 fy_materials 使用旧字段 publish_trace_code，将自动重命名为 publish_random_str")
        else:
            alter_stmts.append("ALTER TABLE fy_materials ADD COLUMN publish_random_str VARCHAR(32) DEFAULT NULL COMMENT '发布随机字符'")
            logger.info("检测到 fy_materials 缺失字段 publish_random_str，将自动添加")
    await _apply_alter_statements(conn, "fy_materials", alter_stmts)
    await _ensure_index(
        conn,
        "fy_materials",
        "idx_fy_material_account",
        ["account_id"],
        "CREATE INDEX idx_fy_material_account ON fy_materials (account_id)",
    )
    await _ensure_index(
        conn,
        "fy_materials",
        "idx_fy_material_owner_account_publish_status",
        ["owner_id", "account_id", "publish_status"],
        "CREATE INDEX idx_fy_material_owner_account_publish_status ON fy_materials (owner_id, account_id, publish_status)",
    )
    if publish_status_added or published_added:
        await conn.execute(
            text(
                "UPDATE fy_materials "
                "SET publish_status = CASE "
                "WHEN LOWER(TRIM(COALESCE(publish_status, ''))) = :published THEN :published "
                "WHEN LOWER(TRIM(COALESCE(publish_status, ''))) = :failed THEN :failed "
                "WHEN published = 1 THEN :published "
                "ELSE :unpublished END"
            ),
            {
                "published": PUBLISH_STATUS_PUBLISHED,
                "failed": PUBLISH_STATUS_FAILED,
                "unpublished": PUBLISH_STATUS_UNPUBLISHED,
            },
        )
        await conn.execute(
            text(
                "UPDATE fy_materials "
                "SET published = CASE WHEN publish_status = :published THEN 1 ELSE 0 END"
            ),
            {"published": PUBLISH_STATUS_PUBLISHED},
        )
        await conn.commit()
    return {
        "account_id_added": account_id_added,
        "publish_status_added": publish_status_added,
        "published_added": published_added,
    }


async def _check_publish_rules_columns(conn: AsyncConnection, existing_tables: list[str]) -> None:
    """检查 fy_publish_rules 表是否缺失发布规则运行字段。"""
    if "fy_publish_rules" not in existing_tables:
        return
    columns = await _get_table_columns(conn, "fy_publish_rules")
    alter_stmts = []
    if "owner_id" not in columns:
        alter_stmts.append("ALTER TABLE fy_publish_rules ADD COLUMN owner_id BIGINT NOT NULL DEFAULT 0 COMMENT '所属用户ID'")
        logger.info("检测到 fy_publish_rules 缺失字段 owner_id，将自动添加")
    if "rule_name" not in columns:
        alter_stmts.append("ALTER TABLE fy_publish_rules ADD COLUMN rule_name VARCHAR(120) NOT NULL DEFAULT '' COMMENT '规则名称'")
        logger.info("检测到 fy_publish_rules 缺失字段 rule_name，将自动添加")
    if "account_id" not in columns:
        alter_stmts.append("ALTER TABLE fy_publish_rules ADD COLUMN account_id VARCHAR(80) NOT NULL DEFAULT '' COMMENT '闲鱼账号ID（xy_accounts.account_id）'")
        logger.info("检测到 fy_publish_rules 缺失字段 account_id，将自动添加")
    if "daily_count" not in columns:
        alter_stmts.append("ALTER TABLE fy_publish_rules ADD COLUMN daily_count INT DEFAULT 5 COMMENT '每天发布数量'")
        logger.info("检测到 fy_publish_rules 缺失字段 daily_count，将自动添加")
    if "enabled" not in columns:
        alter_stmts.append("ALTER TABLE fy_publish_rules ADD COLUMN enabled TINYINT(1) DEFAULT 1 COMMENT '是否启用'")
        logger.info("检测到 fy_publish_rules 缺失字段 enabled，将自动添加")
    if "remark" not in columns:
        alter_stmts.append("ALTER TABLE fy_publish_rules ADD COLUMN remark VARCHAR(255) DEFAULT NULL COMMENT '备注'")
        logger.info("检测到 fy_publish_rules 缺失字段 remark，将自动添加")
    if "last_run_at" not in columns:
        alter_stmts.append("ALTER TABLE fy_publish_rules ADD COLUMN last_run_at DATETIME DEFAULT NULL COMMENT '最后执行时间'")
        logger.info("检测到 fy_publish_rules 缺失字段 last_run_at，将自动添加")
    if "last_run_date" not in columns:
        alter_stmts.append("ALTER TABLE fy_publish_rules ADD COLUMN last_run_date DATE DEFAULT NULL COMMENT '最后执行日期（用于判断今天是否已完成）'")
        logger.info("检测到 fy_publish_rules 缺失字段 last_run_date，将自动添加")
    if "today_count" not in columns:
        alter_stmts.append("ALTER TABLE fy_publish_rules ADD COLUMN today_count INT DEFAULT 0 COMMENT '今天已发布数量'")
        logger.info("检测到 fy_publish_rules 缺失字段 today_count，将自动添加")
    if "created_at" not in columns:
        alter_stmts.append("ALTER TABLE fy_publish_rules ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'")
        logger.info("检测到 fy_publish_rules 缺失字段 created_at，将自动添加")
    if "updated_at" not in columns:
        alter_stmts.append("ALTER TABLE fy_publish_rules ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'")
        logger.info("检测到 fy_publish_rules 缺失字段 updated_at，将自动添加")
    await _apply_alter_statements(conn, "fy_publish_rules", alter_stmts)
    duplicate_result = await conn.execute(
        text(
            "SELECT owner_id, account_id, COUNT(*) AS duplicate_count "
            "FROM fy_publish_rules "
            "GROUP BY owner_id, account_id "
            "HAVING COUNT(*) > 1 "
            "LIMIT 1"
        )
    )
    duplicate_row = duplicate_result.first()
    if duplicate_row:
        logger.warning(
            f"检测到 fy_publish_rules 存在重复账号规则，暂不自动创建唯一约束: owner_id={duplicate_row[0]}, account_id={duplicate_row[1]}"
        )
        return
    await _ensure_unique_constraint(
        conn,
        "fy_publish_rules",
        "uq_fy_publish_rules_owner_account",
        ["owner_id", "account_id"],
        "CREATE UNIQUE INDEX uq_fy_publish_rules_owner_account ON fy_publish_rules (owner_id, account_id)",
    )


async def _check_delete_rules_columns(conn: AsyncConnection, existing_tables: list[str]) -> None:
    """检查 fy_delete_rules 表是否缺失删除规则运行字段。"""
    if "fy_delete_rules" not in existing_tables:
        return
    columns = await _get_table_columns(conn, "fy_delete_rules")
    alter_stmts = []
    if "owner_id" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN owner_id BIGINT NOT NULL DEFAULT 0 COMMENT '所属用户ID'")
        logger.info("检测到 fy_delete_rules 缺失字段 owner_id，将自动添加")
    if "rule_name" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN rule_name VARCHAR(120) NOT NULL DEFAULT '' COMMENT '规则名称'")
        logger.info("检测到 fy_delete_rules 缺失字段 rule_name，将自动添加")
    if "account_id" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN account_id VARCHAR(80) NOT NULL DEFAULT '' COMMENT '闲鱼账号ID（xy_accounts.account_id）'")
        logger.info("检测到 fy_delete_rules 缺失字段 account_id，将自动添加")
    if "daily_count" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN daily_count INT DEFAULT 5 COMMENT '每天删除数量'")
        logger.info("检测到 fy_delete_rules 缺失字段 daily_count，将自动添加")
    if "min_publish_days" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN min_publish_days INT DEFAULT 7 COMMENT '发布满多少天才能删除'")
        logger.info("检测到 fy_delete_rules 缺失字段 min_publish_days，将自动添加")
    if "enabled" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN enabled TINYINT(1) DEFAULT 1 COMMENT '是否启用'")
        logger.info("检测到 fy_delete_rules 缺失字段 enabled，将自动添加")
    if "remark" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN remark VARCHAR(255) DEFAULT NULL COMMENT '备注'")
        logger.info("检测到 fy_delete_rules 缺失字段 remark，将自动添加")
    if "last_run_at" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN last_run_at DATETIME DEFAULT NULL COMMENT '最后执行时间'")
        logger.info("检测到 fy_delete_rules 缺失字段 last_run_at，将自动添加")
    if "last_run_date" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN last_run_date DATE DEFAULT NULL COMMENT '最后执行日期'")
        logger.info("检测到 fy_delete_rules 缺失字段 last_run_date，将自动添加")
    if "today_count" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN today_count INT DEFAULT 0 COMMENT '今天已删除数量'")
        logger.info("检测到 fy_delete_rules 缺失字段 today_count，将自动添加")
    if "total_deleted_count" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN total_deleted_count INT DEFAULT 0 COMMENT '累计删除数量'")
        logger.info("检测到 fy_delete_rules 缺失字段 total_deleted_count，将自动添加")
    if "created_at" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'")
        logger.info("检测到 fy_delete_rules 缺失字段 created_at，将自动添加")
    if "updated_at" not in columns:
        alter_stmts.append("ALTER TABLE fy_delete_rules ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'")
        logger.info("检测到 fy_delete_rules 缺失字段 updated_at，将自动添加")
    await _apply_alter_statements(conn, "fy_delete_rules", alter_stmts)
    # 确保同账号唯一约束
    duplicate_result = await conn.execute(
        text(
            "SELECT owner_id, account_id, COUNT(*) AS duplicate_count "
            "FROM fy_delete_rules "
            "GROUP BY owner_id, account_id "
            "HAVING COUNT(*) > 1 "
            "LIMIT 1"
        )
    )
    duplicate_row = duplicate_result.first()
    if duplicate_row:
        logger.warning(
            f"检测到 fy_delete_rules 存在重复账号规则，暂不自动创建唯一约束: owner_id={duplicate_row[0]}, account_id={duplicate_row[1]}"
        )
        return
    await _ensure_unique_constraint(
        conn,
        "fy_delete_rules",
        "uq_fy_delete_rules_owner_account",
        ["owner_id", "account_id"],
        "CREATE UNIQUE INDEX uq_fy_delete_rules_owner_account ON fy_delete_rules (owner_id, account_id)",
    )


async def _sync_rule_account_dimensions() -> None:
    """同步历史选品规则到发布账号，并回填素材账号归属。"""
    from app.services.product_rule_service import (
        sync_material_accounts_from_product_rules,
        sync_product_rules_to_publish_accounts,
    )

    async with async_session_maker() as session:
        synced_rules = await sync_product_rules_to_publish_accounts(session=session)
        synced_materials = await sync_material_accounts_from_product_rules(session=session)
        if synced_rules > 0 or synced_materials > 0:
            logger.info(f"历史账号维度同步完成：规则同步{synced_rules}条，素材回填{synced_materials}条")
