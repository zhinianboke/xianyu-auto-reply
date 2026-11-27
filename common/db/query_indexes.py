"""启动时检查并在线补齐 MySQL 查询索引，保留历史表数据。"""
from __future__ import annotations

from time import perf_counter

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import DDLElement


class _AddQueryIndexes(DDLElement):
    """将同一张表的待补索引合并为一次在线 ALTER。"""

    inherit_cache = False

    def __init__(self, table, indexes: list):
        """保存已核对的表和索引定义。"""
        self.table = table
        self.indexes = indexes


@compiles(_AddQueryIndexes, "mysql")
def _compile_add_query_indexes(element, compiler, **kwargs) -> str:
    """用 MySQL 方言转义标识符，要求在线创建索引。"""
    preparer = compiler.preparer
    definitions = []
    for index in element.indexes:
        columns = ", ".join(preparer.format_column(column) for column in index.columns)
        definitions.append(f"ADD INDEX {preparer.quote(index.name)} ({columns})")
    table = preparer.format_table(element.table)
    return f"ALTER TABLE {table} {', '.join(definitions)}, ALGORITHM=INPLACE, LOCK=NONE"


def _is_usable_index(parts: list[dict], columns: list[str]) -> bool:
    """判断已有索引能否支持指定列和创建时间排序。"""
    matched = parts[:len(columns)]
    if [part["COLUMN_NAME"] for part in matched] != columns:
        return False
    if any(
        part["SUB_PART"] is not None or part["INDEX_TYPE"] != "BTREE"
        or part.get("IS_VISIBLE", "YES") != "YES"
        for part in matched
    ):
        return False
    if columns[:2] == ["publish_time", "id"]:
        directions = {part["COLLATION"] for part in matched[:2]}
        return directions in ({"A"}, {"D"})
    if columns == ["owner_id", "created_at", "publish_time", "id"]:
        # 归属等值和采集时间范围用于定位，发布时间排序由查询完成。
        return all(part["COLLATION"] in ("A", "D") for part in matched)
    if "created_at" not in columns:
        return True
    ordered = matched[columns.index("created_at"):]
    if columns == ["owner_id", "created_at"]:
        # 额外字段不能插在创建时间与主键之间，否则不能保证同秒排序。
        if len(parts) == len(columns) and matched[0]["ENGINE"] == "InnoDB":
            ordered = [*ordered, {"COLLATION": "A"}]
        elif len(parts) > len(columns):
            primary_part = parts[len(columns)]
            if primary_part["COLUMN_NAME"] != "id" or not _is_usable_index([primary_part], ["id"]):
                return False
            ordered = [*ordered, primary_part]
        else:
            return False
    directions = {part["COLLATION"] for part in ordered}
    return directions in ({"A"}, {"D"})


async def _find_missing_indexes(conn, table, index_names: tuple[str, ...], label: str) -> list:
    """读取当前索引元数据并返回尚未覆盖的模型索引。"""
    result = await conn.execute(text(
        "SELECT s.INDEX_NAME, s.SEQ_IN_INDEX, s.COLUMN_NAME, s.SUB_PART, "
        "s.INDEX_TYPE, s.COLLATION, t.ENGINE /*!80000 , s.IS_VISIBLE */ "
        "FROM information_schema.STATISTICS s "
        "JOIN information_schema.TABLES t ON t.TABLE_SCHEMA=s.TABLE_SCHEMA "
        "AND t.TABLE_NAME=s.TABLE_NAME WHERE s.TABLE_SCHEMA=DATABASE() "
        "AND s.TABLE_NAME=:table_name ORDER BY s.INDEX_NAME, s.SEQ_IN_INDEX"
    ), {"table_name": table.name})
    existing = {}
    for part in result.mappings().all():
        existing.setdefault(part["INDEX_NAME"], []).append(dict(part))
    indexes = {index.name: index for index in table.indexes}
    missing = []
    for name in index_names:
        index = indexes[name]
        columns = [column.name for column in index.columns]
        if name in existing:
            if not _is_usable_index(existing[name], columns):
                message = f"{label}索引 {name} 的字段、长度、可见性或排序不兼容，请核对表结构"
                logger.error(message)
                raise RuntimeError(message)
            continue
        if any(_is_usable_index(value, columns) for value in existing.values()):
            continue
        missing.append(index)
    return missing


async def ensure_query_indexes(conn, table, index_names: tuple[str, ...], *, label: str) -> None:
    """在启动自检的 DDL 连接中在线补齐查询索引。"""
    missing = await _find_missing_indexes(conn, table, index_names, label)
    while missing:
        names = [index.name for index in missing]
        started = perf_counter()
        logger.info(
            "{}索引开始创建: indexes={}, algorithm=INPLACE, lock=NONE; "
            "多个缺失索引合并扫描，大表构建可能耗时较长，锁等待超时不限制构建时间",
            label, names,
        )
        try:
            await conn.execute(_AddQueryIndexes(table, missing))
        except DBAPIError as error:
            # 启动锁等待超时后可能继续自检；同名索引由另一进程建成时，重新核对剩余项。
            if error.orig.args and error.orig.args[0] == 1061:
                pending = await _find_missing_indexes(conn, table, index_names, label)
                if len(pending) < len(missing):
                    missing = pending
                    continue
            logger.exception("{}索引创建失败: indexes={}", label, names)
            raise
        except Exception:
            logger.exception("{}索引创建失败: indexes={}", label, names)
            raise
        logger.info("{}索引创建成功: indexes={}, duration_seconds={:.1f}",
                    label, names, perf_counter() - started)
        break
    logger.info("{}索引自检完成", label)
