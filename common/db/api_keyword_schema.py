"""API关键词数据库自检，由init_database统一调用，幂等补齐表、字段、索引和字典。"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.schema import CreateColumn, CreateIndex

from common.models.data_dictionary import XYDataDictionary
from common.models.xy_api_keyword_rule import (
    HTTP_METHOD_DICTIONARY,
    PARAMETER_DICTIONARY,
    XYApiKeywordRule,
)
from common.utils.time_utils import get_beijing_now_naive


async def ensure_api_keyword_schema(conn: AsyncConnection) -> None:
    """补齐API配置结构和字典，升级原始actId文案，保留配置及自定义字典内容。

    Args:
        conn: 统一初始化入口提供的、持有初始化锁的数据库连接。
    Returns:
        无返回值，失败向初始化入口抛出异常并阻止带病启动。
    """
    table = XYApiKeywordRule.__table__
    await conn.run_sync(lambda sync_conn: table.create(sync_conn, checkfirst=True))
    columns = set((await conn.execute(text(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name"
    ), {"table_name": table.name})).scalars())
    for column in table.columns:
        if column.name not in columns:
            # 标识符和DDL来自固定ORM定义，业务输入不参与构建SQL。
            definition = str(CreateColumn(column).compile(dialect=conn.dialect))
            if column.primary_key:
                definition += " PRIMARY KEY"
            await conn.execute(text(f"ALTER TABLE `{table.name}` ADD COLUMN {definition}"))
            logger.info("API关键词字段已补齐: {}.{}", table.name, column.name)

    indexes = set((await conn.execute(text(
        "SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name"
    ), {"table_name": table.name})).scalars())
    for index in table.indexes:
        if index.name not in indexes:
            await conn.execute(CreateIndex(index))
            logger.info("API关键词索引已补齐: {}", index.name)

    dictionary_rows = (
        (HTTP_METHOD_DICTIONARY, "GET", "GET 请求", 10),
        (HTTP_METHOD_DICTIONARY, "POST", "POST 请求", 20),
        (PARAMETER_DICTIONARY, "item_id", "商品ID", 10),
        (PARAMETER_DICTIONARY, "message", "消息内容", 20),
        (PARAMETER_DICTIONARY, "actId", "消息链接（actId）", 30),
    )
    now = get_beijing_now_naive()
    existing = set((await conn.execute(select(
        XYDataDictionary.dict_type, XYDataDictionary.dict_value,
    ).where(XYDataDictionary.dict_type.in_((HTTP_METHOD_DICTIONARY, PARAMETER_DICTIONARY))))).all())
    for dict_type, value, label, sort_order in dictionary_rows:
        if (dict_type, value) not in existing:
            await conn.execute(insert(XYDataDictionary).values(
                dict_type=dict_type, dict_value=value, dict_label=label, sort_order=sort_order,
                enabled=True, created_at=now, updated_at=now,
            ))
    # 仅升级系统原始文案，保留管理员自定义名称和启用状态；重复自检不会再次修改。
    await conn.execute(update(XYDataDictionary).where(
        XYDataDictionary.dict_type == PARAMETER_DICTIONARY,
        XYDataDictionary.dict_value == "actId",
        XYDataDictionary.dict_label == "消息内容（actId）",
    ).values(dict_label="消息链接（actId）", updated_at=now))
    logger.info("API关键词配置表、字段、索引及参数字典自检完成")
