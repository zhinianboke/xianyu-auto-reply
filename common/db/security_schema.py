"""安全频率迁移：幂等补表、缺字段、唯一索引、字典和默认配置，保留历史值。"""
from __future__ import annotations

from sqlalchemy import DefaultClause, Index, UniqueConstraint, inspect, select, text
from sqlalchemy.schema import CreateColumn

from common.db.idempotent_insert import insert_defaults
from common.models.data_dictionary import XYDataDictionary
from common.models.scheduled_task import ScheduledTask
from common.models.security_log import SecurityLog
from common.models.security_task import (
    SECURITY_DICTIONARIES,
    SECURITY_INTERVAL_SECONDS,
    SECURITY_TASK_CODE,
    SecurityTask,
)
from common.models.system_setting import SystemSetting
from common.services.security_config_service import ensure_security_defaults
from common.utils.time_utils import get_beijing_now_naive


async def _ensure_table(connection, table) -> None:
    """由统一迁移连接创建新表，旧表只补结构；缺失历史字段保持NULL。"""
    await connection.run_sync(lambda sync: table.create(sync, checkfirst=True))
    if table.name in (ScheduledTask.__tablename__, SecurityTask.__tablename__, SecurityLog.__tablename__):
        await _ensure_storage_options(connection, table)
    primary_key = await connection.run_sync(lambda sync: inspect(sync).get_pk_constraint(table.name))
    expected_pk = [column.name for column in table.primary_key.columns]
    if primary_key.get('constrained_columns') != expected_pk:
        raise RuntimeError(f'{table.comment or table.name}主键结构无效，请先备份并修复结构')
    columns = await connection.run_sync(lambda sync: inspect(sync).get_columns(table.name))
    existing = {item['name'] for item in columns}
    for column in table.columns:
        if column.name in existing:
            continue
        if column.primary_key:
            raise RuntimeError(f'{table.comment}缺少主键，请先备份并修复结构')
        copy = column._copy()
        copy.nullable, copy.default, copy.server_default = True, None, None
        if table.name == ScheduledTask.__tablename__ and column.name in ('created_at', 'updated_at'):
            copy.comment = '创建时间' if column.name == 'created_at' else '更新时间'
        if table.name == SecurityTask.__tablename__ and column.name in ('interval_seconds', 'config_version', 'enabled'):
            # 新增运行配置采用真实默认值；历史执行时间及结果仍保持NULL，不推测补造。
            copy.nullable = False
            copy.server_default = DefaultClause('0' if column.name == 'enabled' else str(column.default.arg))
        ddl = str(CreateColumn(copy).compile(dialect=connection.dialect))
        preparer = connection.dialect.identifier_preparer
        await connection.execute(text(f'ALTER TABLE {preparer.quote(table.name)} ADD COLUMN {ddl}'))
    await _ensure_indexes(connection, table)


async def _ensure_indexes(connection, table) -> None:
    """核对真实索引列及唯一性；缺失则补齐，同名错误结构明确拒绝且不删除历史索引。"""
    indexes = await connection.run_sync(lambda sync: inspect(sync).get_indexes(table.name))
    constraints = await connection.run_sync(lambda sync: inspect(sync).get_unique_constraints(table.name))
    existing = indexes + [dict(item, unique=True) for item in constraints]
    required = list(table.indexes) + [item for item in table.constraints if isinstance(item, UniqueConstraint)]
    for item in required:
        expected_columns = [column.name for column in item.columns]
        expected_unique = isinstance(item, UniqueConstraint) or bool(item.unique)
        matches = [actual for actual in existing if actual['name'] == item.name]
        if matches:
            if any(actual['column_names'] != expected_columns or bool(actual.get('unique')) != expected_unique
                   or any(actual.get('dialect_options', {}).get(option) is not None
                          for option in ('sqlite_where', 'mysql_length'))
                   or any('desc' in sorting for sorting in actual.get('column_sorting', {}).values())
                   for actual in matches):
                raise RuntimeError(f'{table.comment or table.name}索引{item.name}结构无效，'
                                   f'应为列{expected_columns}、唯一性{expected_unique}，'
                                   '不得使用条件索引、前缀索引或降序列，'
                                   '请先备份并由管理员修复结构；程序未删除或替换原索引')
            continue
        index = item if isinstance(item, Index) else Index(item.name, *item.columns, unique=True)
        try:
            await connection.run_sync(lambda sync, index=index: index.create(sync, checkfirst=True))
        finally:
            if isinstance(item, UniqueConstraint):
                # 临时补建对象不得积累进公共模型，否则重复自检会增长元数据索引集合。
                table.indexes.discard(index)


async def _ensure_storage_options(connection, table) -> None:
    """事务锁与审计依赖InnoDB及utf8mb4；既存不兼容表明确报错，不自动转换。"""
    if connection.dialect.name != 'mysql':
        return
    engine, collation = (await connection.execute(text(
        'SELECT ENGINE, TABLE_COLLATION FROM information_schema.TABLES '
        'WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table'
    ), {'table': table.name})).one()
    columns = (await connection.execute(text(
        'SELECT COLUMN_NAME, CHARACTER_SET_NAME FROM information_schema.COLUMNS '
        'WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table '
        'AND CHARACTER_SET_NAME IS NOT NULL AND CHARACTER_SET_NAME <> :charset'
    ), {'table': table.name, 'charset': 'utf8mb4'})).all()
    if str(engine).lower() != 'innodb' or not str(collation).lower().startswith('utf8mb4_') or columns:
        raise RuntimeError(f'{table.comment}引擎或字符集不兼容：{engine!r}、{collation!r}、{columns!r}；'
                           '请停止写入、备份后由管理员迁移至InnoDB和utf8mb4，程序不自动转换历史表')


async def ensure_security_schema(connection) -> None:
    """补齐安全结构、三类字典及默认项；冲突只保留原名称、排序、状态和值。"""
    for table in (SecurityTask.__table__, SecurityLog.__table__):
        await _ensure_table(connection, table)
    # 安全字典的唯一键也是并发幂等默认插入前置条件，启动时一并补齐。
    await _ensure_table(connection, XYDataDictionary.__table__)
    if connection.dialect.name == 'mysql':
        await _ensure_storage_options(connection, SystemSetting.__table__)
        for table, names in ((SystemSetting.__table__, ('value',)), (SecurityTask.__table__, ('last_message',)),
                             (SecurityLog.__table__, ('message', 'added_suffixes', 'added_ips', 'details'))):
            await _ensure_longtext_columns(connection, table, names)
    now = get_beijing_now_naive()
    for dict_type, entries in SECURITY_DICTIONARIES.items():
        for sort, (value, label) in enumerate(entries, 1):
            await insert_defaults(connection, XYDataDictionary.__table__, {
                'dict_type': dict_type, 'dict_value': value, 'dict_label': label,
                'sort_order': sort * 10, 'enabled': True, 'created_at': now, 'updated_at': now,
            }, ('dict_type', 'dict_value'))
    await ensure_security_defaults(connection)
    await _ensure_scheduled_security_task(connection)


async def _ensure_scheduled_security_task(connection) -> None:
    """仅向原任务表补安全任务；原表已有配置优先，旧安全状态和历史日志保持原样。"""
    table = ScheduledTask.__table__
    await _ensure_table(connection, table)
    # 保留曾经保存的旧开关；全新部署及旧表缺开关时由安全默认项提供False。
    enabled = (await connection.execute(select(SecurityTask.enabled).where(
        SecurityTask.task_code == SECURITY_TASK_CODE))).scalar_one()
    name = (await connection.execute(select(XYDataDictionary.dict_label).where(
        XYDataDictionary.dict_type == 'security_task_name',
        XYDataDictionary.dict_value == SECURITY_TASK_CODE))).scalar_one()
    now = get_beijing_now_naive()
    await insert_defaults(connection, table, {
        'task_code': SECURITY_TASK_CODE, 'task_name': name, 'interval_seconds': SECURITY_INTERVAL_SECONDS,
        'enabled': bool(enabled), 'description': '检查注册、邮件和登录频率；频率阈值在安全设置中配置，详情见安全日志。',
        'created_at': now, 'updated_at': now,
    }, ('task_code',))


async def _ensure_longtext_columns(connection, table, names) -> None:
    """只扩容完整名单和审计文本，沿用真实列的NULL属性，不截断或改写历史内容。"""
    columns = (await connection.execute(text(
        'SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE FROM information_schema.COLUMNS '
        'WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table'
    ), {'table': table.name})).all()
    types = {name: (data_type, nullable) for name, data_type, nullable in columns}
    preparer = connection.dialect.identifier_preparer
    for name in names:
        data_type, nullable = types[name]
        if data_type.lower() == 'longtext':
            continue
        # 标识符及COMMENT只来自统一模型，不接受请求参数或数据库内容拼接SQL。
        column = table.c[name]._copy()
        column.nullable, column.default, column.server_default = nullable == 'YES', None, None
        ddl = str(CreateColumn(column).compile(dialect=connection.dialect))
        await connection.execute(text(f'ALTER TABLE {preparer.quote(table.name)} MODIFY COLUMN {ddl}'))
