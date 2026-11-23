"""认证安全设置启动自检：幂等补分组字段、配置及中文说明，仅迁移旧配置分组。"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import inspect, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from common.models.system_setting import SystemSetting
from common.db.idempotent_insert import insert_defaults
from common.db.security_schema import ensure_security_schema
from common.services.auth_security_policy import (
    AUTH_SECURITY_DEFAULTS,
    AUTH_SECURITY_GROUP,
)
from common.utils.time_utils import get_beijing_now_naive


async def ensure_auth_security_schema(conn: AsyncConnection) -> None:
    """补齐安全配置结构和初始值；保留原键和值，已有记录只幂等调整安全分组。

    Args:
        conn: 统一启动自检提供的连接，生产环境持有数据库初始化锁。
    Returns:
        无返回值；数据库失败向启动入口传播，不允许缺少安全配置结构时继续启动。
    """
    table = SystemSetting.__table__
    await conn.run_sync(lambda sync_conn: table.create(sync_conn, checkfirst=True))
    columns = {column['name'] for column in await conn.run_sync(lambda sync: inspect(sync).get_columns(table.name))}
    if 'group' not in columns:
        ddl = "ALTER TABLE xy_system_settings ADD COLUMN `group` VARCHAR(32) NULL"
        if conn.dialect.name == 'mysql':
            ddl += " COMMENT '设置分组'"
        await conn.execute(text(ddl))
        logger.info('安全设置字段已补齐：xy_system_settings.group')
    # 先验证安全存储及事务前置条件，旧表不兼容时禁止先修改已有配置分组。
    await ensure_security_schema(conn)
    rows = (await conn.execute(select(
        SystemSetting.key, SystemSetting.group, SystemSetting.description,
    ).where(SystemSetting.key.in_(tuple(AUTH_SECURITY_DEFAULTS))))).all()
    existing = {key: (group, description) for key, group, description in rows}
    now = get_beijing_now_naive()
    for key, (value, description) in AUTH_SECURITY_DEFAULTS.items():
        if key not in existing:
            await insert_defaults(conn, table, {
                'key': key, 'value': value, 'description': description,
                'group': AUTH_SECURITY_GROUP, 'updated_at': now,
            }, ('key',))
        else:
            group, old_description = existing[key]
            changes = {}
            if group != AUTH_SECURITY_GROUP:
                changes['group'] = AUTH_SECURITY_GROUP
            if not old_description:
                changes['description'] = description
            if changes:
                # 明确保留更新时间，避免元数据分组迁移改变历史配置内容修改时间。
                await conn.execute(update(SystemSetting).where(SystemSetting.key == key).values(
                    **changes, updated_at=SystemSetting.updated_at,
                ))
    logger.info('认证安全设置、频率任务、审计结构及字典自检完成；原键、值及历史更新时间保持不变')
