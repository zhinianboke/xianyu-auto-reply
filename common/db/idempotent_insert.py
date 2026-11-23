"""数据库默认记录并发插入：只忽略目标唯一键冲突，不覆盖原值或吞掉其他错误。"""
from __future__ import annotations

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


async def insert_defaults(connection, table, values: dict, unique_columns: tuple[str, ...]) -> None:
    """在调用方事务插入缺省项；MySQL和SQLite使用原子唯一键冲突处理。"""
    dialect = connection.dialect.name if hasattr(connection, 'dialect') else connection.get_bind().dialect.name
    if dialect == 'mysql':
        statement = mysql_insert(table).values(**values)
        # 原值自赋值，不触发ORM onupdate，所有既存值包括更新时间保持原样。
        statement = statement.on_duplicate_key_update(**{unique_columns[0]: table.c[unique_columns[0]]})
    elif dialect == 'sqlite':
        statement = sqlite_insert(table).values(**values).on_conflict_do_nothing(index_elements=unique_columns)
    else:
        raise RuntimeError('安全配置只支持MySQL与SQLite数据库')
    await connection.execute(statement)
