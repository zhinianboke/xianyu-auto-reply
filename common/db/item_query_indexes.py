"""商品查询索引变更：启动时幂等补齐索引，只增加索引，不改写历史数据。"""
from __future__ import annotations

from time import perf_counter

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import DDLElement

from common.models.xy_catalog_item import XYCatalogItem


ITEM_QUERY_INDEX_NAMES = (
    "idx_cat_created_id",
    "idx_cat_account_created_id",
    "idx_cat_owner_created",
    "idx_item_id",
)


class _AddItemQueryIndexes(DDLElement):
    """保存来自商品 ORM 模型的待建索引，供 MySQL 编译为单次在线 ALTER。"""

    inherit_cache = False

    def __init__(self, indexes: list):
        """接收已检查的模型索引列表，无返回值。"""
        self.indexes = indexes


@compiles(_AddItemQueryIndexes, "mysql")
def _compile_add_item_query_indexes(element, compiler, **kwargs) -> str:
    """用方言转义模型标识符，返回合并索引且禁止退回 COPY/锁表算法的 DDL。"""
    preparer = compiler.preparer
    definitions = []
    for index in element.indexes:
        columns = ", ".join(preparer.format_column(column) for column in index.columns)
        definitions.append(f"ADD INDEX {preparer.quote(index.name)} ({columns})")
    table = preparer.format_table(XYCatalogItem.__table__)
    return f"ALTER TABLE {table} {', '.join(definitions)}, ALGORITHM=INPLACE, LOCK=NONE"


def _is_usable_index(parts: list[dict], columns: list[str]) -> bool:
    """判断已有索引是否覆盖目标字段及排序；参数为索引元数据和字段，返回布尔值。"""
    matched = parts[:len(columns)]
    if [part["COLUMN_NAME"] for part in matched] != columns:
        return False
    if any(
        part["SUB_PART"] is not None or part["INDEX_TYPE"] != "BTREE"
        or part.get("IS_VISIBLE", "YES") != "YES"
        for part in matched
    ):
        return False
    if "created_at" not in columns:
        return True
    ordered = matched[columns.index("created_at"):]
    if columns == ["owner_id", "created_at"]:
        # InnoDB 的两列二级索引隐含升序主键；额外字段不能插在创建时间与主键之间。
        if len(parts) == len(columns) and matched[0]["ENGINE"] == "InnoDB":
            ordered = [*ordered, {"COLLATION": "A"}]
        elif len(parts) > len(columns):
            primary_part = parts[len(columns)]
            if primary_part["COLUMN_NAME"] != "id" or not _is_usable_index(
                [primary_part], ["id"]
            ):
                return False
            ordered = [*ordered, primary_part]
        else:
            return False
    directions = {part["COLLATION"] for part in ordered}
    return directions in ({"A"}, {"D"})


async def ensure_item_query_indexes(conn) -> None:
    """使用已有 DDL 连接补齐商品查询索引。

    Args:
        conn: 启动自检持有命名锁并设置锁等待上限后的数据库连接。
    Returns:
        无返回值；建索引失败记录完整异常并中止启动，避免静默跳过。
    """
    result = await conn.execute(text(
        "SELECT s.INDEX_NAME, s.SEQ_IN_INDEX, s.COLUMN_NAME, s.SUB_PART, "
        "s.INDEX_TYPE, s.COLLATION, t.ENGINE /*!80000 , s.IS_VISIBLE */ "
        "FROM information_schema.STATISTICS s "
        "JOIN information_schema.TABLES t ON t.TABLE_SCHEMA=s.TABLE_SCHEMA "
        "AND t.TABLE_NAME=s.TABLE_NAME WHERE s.TABLE_SCHEMA=DATABASE() "
        "AND s.TABLE_NAME=:table_name ORDER BY s.INDEX_NAME, s.SEQ_IN_INDEX"
    ), {"table_name": XYCatalogItem.__tablename__})
    existing = {}
    for part in result.mappings().all():
        existing.setdefault(part["INDEX_NAME"], []).append(dict(part))
    indexes = {index.name: index for index in XYCatalogItem.__table__.indexes}
    missing = []
    for name in ITEM_QUERY_INDEX_NAMES:
        index = indexes[name]
        columns = [column.name for column in index.columns]
        # 已有同名索引或等价前缀索引均跳过，避免重复建索引。
        if name in existing:
            if not _is_usable_index(existing[name], columns):
                message = f"商品查询索引 {name} 的字段、长度、可见性或排序不兼容，请核对表结构"
                logger.error(message)
                raise RuntimeError(message)
            continue
        if any(_is_usable_index(value, columns) for value in existing.values()):
            continue
        missing.append(index)
    if missing:
        names = [index.name for index in missing]
        started = perf_counter()
        logger.info(
            "商品查询索引开始创建: indexes={}, algorithm=INPLACE, lock=NONE; "
            "多个缺失索引合并扫描，大表构建可能耗时较长，锁等待超时不限制构建时间",
            names,
        )
        try:
            await conn.execute(_AddItemQueryIndexes(missing))
        except Exception:
            logger.exception("商品查询索引创建失败: indexes={}", names)
            raise
        logger.info("商品查询索引创建成功: indexes={}, duration_seconds={:.1f}",
                    names, perf_counter() - started)
    logger.info("商品查询索引自检完成")
