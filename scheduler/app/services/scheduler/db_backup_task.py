"""
数据库备份定时任务

功能：
1. 默认每小时执行一次，备份数据库中所有表的表结构与表数据
2. 使用纯 Python（异步会话）导出，不依赖容器内 mysqldump 二进制
3. 导出内容写入 .sql.gz 压缩文件，存放到共享备份目录（由 BACKUP_DIR 环境变量管理）
4. 每次执行写一条备份日志（成功/失败、文件名、路径、大小、表数、行数、耗时）

设计要点：
- 逐表导出：先 SHOW CREATE TABLE 写建表语句，再分批 SELECT 写 INSERT 语句
- 分批读取（每批 1000 行），避免大表一次性载入内存
- 单表失败不中断整体备份，记录到错误信息中
- 备份属于只读导出，绝不修改/删除任何业务数据
"""
from __future__ import annotations

import gzip
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.config import get_settings
from common.db.retry import with_db_retry
from common.db.session import async_engine, async_session_maker
from common.models.db_backup_log import DbBackupLog
from common.utils.backup_paths import ensure_backup_root, get_backup_root
from common.utils.time_utils import get_beijing_now, get_beijing_now_naive

# 每批读取的数据行数，避免大表一次性载入内存
_BATCH_SIZE = 1000

# 备份文件与备份日志的保留天数，超过该天数的备份文件与日志记录会被自动清理
_RETENTION_DAYS = 10


class DbBackupTaskService:
    """数据库备份定时任务服务"""

    def __init__(self):
        self.task_name = "数据库备份"

    async def execute(self) -> None:
        """执行一次数据库备份。"""
        logger.info(f"【{self.task_name}】开始执行")
        start_time = time.monotonic()

        settings = get_settings()
        database = settings.mysql_database

        backup_root = ensure_backup_root()
        now = get_beijing_now()
        file_name = f"backup_{database}_{now.strftime('%Y%m%d_%H%M%S')}.sql.gz"
        file_path = backup_root / file_name

        table_count = 0
        total_rows = 0
        error_messages: list[str] = []

        try:
            async with async_session_maker() as session:
                tables = await self._list_tables(session, database)
                if not tables:
                    logger.warning(f"【{self.task_name}】未查询到任何数据表，跳过备份")

                # 以 gzip 文本模式写入，边导出边落盘，降低内存占用
                with gzip.open(file_path, "wt", encoding="utf-8") as fp:
                    self._write_header(fp, database, now)
                    for table in tables:
                        try:
                            rows = await self._dump_table(session, fp, table)
                            table_count += 1
                            total_rows += rows
                        except Exception as table_exc:  # 单表失败不中断整体
                            msg = f"表 {table} 备份失败: {str(table_exc)[:200]}"
                            logger.error(f"【{self.task_name}】{msg}")
                            error_messages.append(msg)
                    self._write_footer(fp)

            file_size = file_path.stat().st_size if file_path.exists() else 0
            duration_ms = int((time.monotonic() - start_time) * 1000)

            # 有任何单表失败则记为 failed，但保留已生成的文件供排查
            status = "failed" if error_messages else "success"
            error_text = "; ".join(error_messages)[:1000] if error_messages else None

            await self._log_result(
                status=status,
                file_name=file_name,
                file_path=str(file_path),
                file_size=file_size,
                table_count=table_count,
                total_rows=total_rows,
                duration_ms=duration_ms,
                error_message=error_text,
            )

            logger.info(
                f"【{self.task_name}】执行完成，状态: {status}, 文件: {file_name}, "
                f"表数: {table_count}, 行数: {total_rows}, "
                f"大小: {file_size} 字节, 耗时: {duration_ms} ms"
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            error_text = str(exc)[:1000]
            logger.error(f"【{self.task_name}】执行失败: {error_text}")

            # 失败时清理可能残留的不完整文件
            try:
                if file_path.exists():
                    file_path.unlink()
            except Exception:
                pass

            await self._log_result(
                status="failed",
                file_name=None,
                file_path=None,
                file_size=None,
                table_count=table_count,
                total_rows=total_rows,
                duration_ms=duration_ms,
                error_message=error_text,
            )
        finally:
            # 无论本次备份成败，都清理过期备份（保留最近 N 天），清理失败不影响主流程
            await self._cleanup_expired_backups()

    async def _list_tables(self, session: AsyncSession, database: str) -> list[str]:
        """查询当前数据库下的所有基础表（不含视图）。"""
        stmt = text(
            """
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = :db AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
            """
        )
        result = await session.execute(stmt, {"db": database})
        return [row[0] for row in result.all()]

    @staticmethod
    def _write_header(fp, database: str, now: datetime) -> None:
        """写入备份文件头部信息与会话设置。"""
        fp.write(f"-- 数据库备份文件\n")
        fp.write(f"-- 数据库: {database}\n")
        fp.write(f"-- 备份时间(北京时间): {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
        fp.write("-- 说明: 本文件由定时任务自动生成，包含所有表结构与数据\n\n")
        fp.write("SET NAMES utf8mb4;\n")
        fp.write("SET FOREIGN_KEY_CHECKS=0;\n\n")

    @staticmethod
    def _write_footer(fp) -> None:
        """写入备份文件尾部。"""
        fp.write("\nSET FOREIGN_KEY_CHECKS=1;\n")

    async def _dump_table(self, session: AsyncSession, fp, table: str) -> int:
        """导出单张表的结构与数据，返回导出的数据行数。"""
        # 1. 表结构
        create_stmt = await session.execute(text(f"SHOW CREATE TABLE `{table}`"))
        create_row = create_stmt.first()
        create_sql = create_row[1] if create_row and len(create_row) > 1 else ""

        fp.write(f"\n-- ----------------------------\n")
        fp.write(f"-- 表结构: {table}\n")
        fp.write(f"-- ----------------------------\n")
        fp.write(f"DROP TABLE IF EXISTS `{table}`;\n")
        fp.write(f"{create_sql};\n\n")

        # 2. 表数据（流式读取，避免大表 OFFSET 性能退化与内存占用过高）
        fp.write(f"-- 表数据: {table}\n")
        columns = await self._get_columns(session, table)
        col_clause = ", ".join(f"`{c}`" for c in columns)

        row_count = 0
        # 使用独立连接以服务端游标流式读取，避免一次性把整表载入内存。
        # async 下需用 conn.stream() 获取 AsyncResult，其 partitions() 支持异步迭代分批。
        async with async_engine.connect() as conn:
            stream = await conn.stream(text(f"SELECT * FROM `{table}`"))
            async for partition in stream.partitions(_BATCH_SIZE):
                for row in partition:
                    values = ", ".join(self._format_value(v) for v in row)
                    fp.write(f"INSERT INTO `{table}` ({col_clause}) VALUES ({values});\n")
                row_count += len(partition)

        fp.write("\n")
        return row_count

    async def _get_columns(self, session: AsyncSession, table: str) -> list[str]:
        """按表定义顺序获取列名列表。"""
        stmt = text(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table
            ORDER BY ORDINAL_POSITION
            """
        )
        result = await session.execute(stmt, {"table": table})
        return [row[0] for row in result.all()]

    @staticmethod
    def _format_value(value) -> str:
        """将单个字段值格式化为安全的 SQL 字面量。"""
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (bytes, bytearray)):
            return f"0x{value.hex()}" if value else "''"
        if isinstance(value, datetime):
            return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
        # 其余统一按字符串处理并转义特殊字符，防止破坏 SQL 结构
        text_value = str(value)
        escaped = (
            text_value.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\x00", "")
        )
        return f"'{escaped}'"

    @with_db_retry(max_retries=3, initial_delay=1.0)
    async def _log_result(
        self,
        *,
        status: str,
        file_name: Optional[str],
        file_path: Optional[str],
        file_size: Optional[int],
        table_count: Optional[int],
        total_rows: Optional[int],
        duration_ms: Optional[int],
        error_message: Optional[str],
    ) -> None:
        """写入一条数据库备份日志。"""
        try:
            async with async_session_maker() as session:
                log = DbBackupLog(
                    status=status,
                    file_name=file_name,
                    file_path=file_path,
                    file_size=file_size,
                    table_count=table_count,
                    total_rows=total_rows,
                    duration_ms=duration_ms,
                    error_message=error_message,
                )
                session.add(log)
                await session.commit()
        except Exception as exc:
            logger.error(f"【{self.task_name}】记录备份日志失败: {exc}")

    async def _cleanup_expired_backups(self) -> None:
        """清理过期的备份文件与备份日志记录（保留最近 _RETENTION_DAYS 天）。

        说明：
        - 仅删除备份文件与备份日志记录，绝不触碰任何业务数据表
        - 文件删除依据文件修改时间，日志删除依据 created_at
        - 任意一步失败均不影响本次备份主流程
        """
        cutoff = get_beijing_now() - timedelta(days=_RETENTION_DAYS)

        # 1. 删除过期备份文件
        try:
            backup_root = get_backup_root()
            if backup_root.is_dir():
                cutoff_ts = cutoff.timestamp()
                removed = 0
                for file in backup_root.glob("backup_*.sql.gz"):
                    try:
                        if file.is_file() and file.stat().st_mtime < cutoff_ts:
                            file.unlink()
                            removed += 1
                    except Exception as file_exc:
                        logger.warning(f"【{self.task_name}】删除过期备份文件失败 {file.name}: {file_exc}")
                if removed:
                    logger.info(f"【{self.task_name}】已清理 {removed} 个超过 {_RETENTION_DAYS} 天的备份文件")
        except Exception as exc:
            logger.error(f"【{self.task_name}】清理过期备份文件异常: {exc}")

        # 2. 删除过期备份日志记录
        try:
            cutoff_naive = get_beijing_now_naive() - timedelta(days=_RETENTION_DAYS)
            async with async_session_maker() as session:
                result = await session.execute(
                    delete(DbBackupLog).where(DbBackupLog.created_at < cutoff_naive)
                )
                await session.commit()
                deleted = int(result.rowcount or 0)
                if deleted:
                    logger.info(f"【{self.task_name}】已清理 {deleted} 条超过 {_RETENTION_DAYS} 天的备份日志")
        except Exception as exc:
            logger.error(f"【{self.task_name}】清理过期备份日志异常: {exc}")


# 全局实例
db_backup_task_service = DbBackupTaskService()
