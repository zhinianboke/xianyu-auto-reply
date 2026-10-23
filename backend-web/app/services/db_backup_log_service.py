"""
数据库备份日志查询服务

功能：
1. 数据库备份日志分页查询（按状态、时间范围筛选）
2. 根据日志ID获取备份文件路径，用于下载
3. 删除备份日志及其关联的备份文件
4. 仅管理员可访问（鉴权在路由层处理）
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.retry import with_db_retry
from common.models.db_backup_log import DbBackupLog
from common.utils.backup_paths import get_backup_root, locate_backup_file
from common.utils.pagination import execute_paginated_with_filters
from common.utils.time_utils import safe_isoformat


class DbBackupDeleteError(RuntimeError):
    """删除或恢复备份失败时可直接展示给用户的业务错误。"""


class DbBackupLogService:
    """数据库备份日志只读访问 + 备份文件下载/删除。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_logs(
        self,
        *,
        status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """分页查询数据库备份日志。

        Args:
            status: 备份状态筛选（success / failed）
            start_date: 开始日期（YYYY-MM-DD，含当天 00:00:00）
            end_date: 结束日期（YYYY-MM-DD，含当天 23:59:59）
            limit: 每页数量
            offset: 偏移量

        Returns:
            (日志列表[dict], 总数)
        """
        filters: list = []

        if status:
            if status not in {"success", "failed"}:
                raise ValueError("备份状态只能是 success 或 failed")
            filters.append(DbBackupLog.status == status)

        start_dt = self._parse_filter_date(start_date, "开始日期")
        end_dt = self._parse_filter_date(end_date, "结束日期")
        if start_dt and end_dt and start_dt > end_dt:
            raise ValueError("开始日期不能晚于结束日期")
        if start_dt:
            filters.append(DbBackupLog.created_at >= start_dt)
        if end_dt and end_dt.date() < datetime.max.date():
            # 使用次日零点作为开区间，避免遗漏带微秒的当天最后一秒数据。
            # 最大日期已覆盖所有可存储时间，无需构造超出 datetime 范围的次日。
            filters.append(DbBackupLog.created_at < end_dt + timedelta(days=1))

        logs, total = await execute_paginated_with_filters(
            self.session,
            DbBackupLog,
            filters=filters,
            order_by=[DbBackupLog.created_at.desc()],
            limit=limit,
            offset=offset,
        )

        items = [
            {
                "id": log.id,
                "status": log.status,
                "file_name": log.file_name,
                "file_path": log.file_path,
                "file_size": log.file_size,
                "table_count": log.table_count,
                "total_rows": log.total_rows,
                "duration_ms": log.duration_ms,
                "error_message": log.error_message,
                # 文件真实存在（按文件名或记录路径任一可定位）时才允许下载
                "downloadable": bool(locate_backup_file(log.file_name, log.file_path)),
                "created_at": safe_isoformat(log.created_at),
            }
            for log in logs
        ]
        return items, total

    @staticmethod
    def _parse_filter_date(value: Optional[str], field_name: str) -> Optional[datetime]:
        """解析列表日期条件，无效格式直接返回清晰的业务错误。"""
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"{field_name}格式不正确，应为 YYYY-MM-DD") from exc

    async def get_backup_file(self, log_id: int) -> tuple[Optional[Path], Optional[str]]:
        """根据日志ID解析可下载的备份文件路径。

        Returns:
            (文件路径, 文件名)；当日志不存在或文件不可用时返回 (None, None)。
        """
        result = await self.session.execute(
            select(DbBackupLog).where(DbBackupLog.id == log_id).with_for_update()
        )
        log = result.scalar_one_or_none()
        if not log or not log.file_name:
            return None, None

        file_path = locate_backup_file(log.file_name, log.file_path)
        if not file_path:
            return None, None
        return file_path, log.file_name

    async def delete_log(self, log_id: int) -> tuple[bool, str, int]:
        """删除备份日志及其关联的备份文件。

        复用批量删除流程，确保单条和批量删除具有相同的文件补偿与事务语义。

        Returns:
            (是否成功, 提示消息, 业务状态码)
        """
        deleted, failed_ids, message = await self.delete_logs([log_id])
        if deleted == 1 and not failed_ids:
            return True, "备份日志已删除", 200
        code = 40002 if deleted > 0 else 40001
        return False, message, code

    @staticmethod
    def _locate_deletable_file(log: DbBackupLog) -> Optional[Path]:
        """仅定位备份根目录内的文件，防止异常历史路径删除目录外文件。"""
        file_path = locate_backup_file(log.file_name, log.file_path)
        if not file_path:
            return None
        try:
            file_path.resolve().relative_to(get_backup_root().resolve())
        except ValueError as exc:
            raise ValueError("备份文件不在当前备份目录中") from exc
        return file_path

    @staticmethod
    def _stage_file_for_delete(file_path: Path, log_id: int) -> tuple[Path, Path]:
        """在同一目录重命名待删文件，数据库提交失败时可恢复。"""
        staged_path = file_path.with_name(
            f".{file_path.name}.{log_id}.{uuid4().hex}.deleting"
        )
        file_path.replace(staged_path)
        return file_path, staged_path

    @staticmethod
    def _restore_staged_file(original_path: Path, staged_path: Path) -> bool:
        """数据库回滚后恢复已暂存的备份文件。"""
        try:
            if staged_path.exists() and original_path.exists():
                raise FileExistsError(f"原备份文件路径已被占用: {original_path}")
            if staged_path.exists():
                staged_path.replace(original_path)
            return original_path.exists() and not staged_path.exists()
        except OSError as exc:
            logger.exception(
                f"恢复暂存备份文件失败 original={original_path} staged={staged_path}: {exc}"
            )
            return False

    @staticmethod
    def _remove_staged_file(staged_path: Path, log_id: int) -> bool:
        """数据库提交成功后清理暂存文件。"""
        try:
            staged_path.unlink(missing_ok=True)
            return not staged_path.exists()
        except OSError as exc:
            logger.exception(f"清理暂存备份文件失败 log_id={log_id} path={staged_path}: {exc}")
            return False

    async def recover_staged_files(self) -> None:
        """根据数据库记录恢复进程中断后遗留的暂存备份文件。"""
        backup_root = get_backup_root()
        if not backup_root.is_dir():
            return

        staged_items: list[tuple[int, Path, Path]] = []
        for staged_path in backup_root.glob(".*.deleting"):
            parts = staged_path.name.rsplit(".", 3)
            if (
                len(parts) != 4
                or not parts[0].startswith(".")
                or len(parts[0]) == 1
                or not parts[1]
                or any(char not in "0123456789" for char in parts[1])
                or len(parts[1]) > 19
                or not 0 < int(parts[1]) <= 2**63 - 1
                or len(parts[2]) != 32
                or any(char not in "0123456789abcdef" for char in parts[2].lower())
                or parts[3] != "deleting"
            ):
                logger.error(f"发现无法识别的备份暂存文件，未自动处理 path={staged_path}")
                continue
            original_path = backup_root / parts[0][1:]
            staged_items.append((int(parts[1]), staged_path, original_path))

        if not staged_items:
            return

        staged_log_ids = {log_id for log_id, _, _ in staged_items}
        existing_log_ids = await self._get_existing_log_ids(staged_log_ids)

        for log_id, staged_path, original_path in staged_items:
            try:
                if log_id in existing_log_ids and not original_path.exists():
                    staged_path.replace(original_path)
                    logger.warning(
                        f"已恢复进程中断时暂存的备份文件 log_id={log_id} path={original_path}"
                    )
                elif log_id in existing_log_ids:
                    logger.error(
                        f"暂存备份文件与现有备份同名，保留暂存文件供检查 "
                        f"log_id={log_id} original={original_path} staged={staged_path}"
                    )
                else:
                    staged_path.unlink(missing_ok=True)
                    logger.info(
                        f"已清理数据库记录不存在的暂存备份文件 "
                        f"log_id={log_id} path={staged_path}"
                    )
            except OSError as exc:
                logger.exception(
                    f"恢复或清理中断暂存备份文件失败 log_id={log_id} "
                    f"original={original_path} staged={staged_path}: {exc}"
                )

    @with_db_retry()
    async def _get_existing_log_ids(self, log_ids: set[int]) -> set[int]:
        """查询仍存在的日志 ID；读取当前事务结果，连接失败时回滚后重试。

        Args:
            log_ids: 需要确认存在状态的日志 ID。
        Returns:
            数据库中仍存在的日志 ID 集合。
        """
        try:
            result = await self.session.execute(
                select(DbBackupLog.id)
                .where(DbBackupLog.id.in_(log_ids))
                .with_for_update()
            )
            return set(result.scalars().all())
        except Exception:
            await self.session.rollback()
            raise

    async def _recover_failed_delete(
        self,
        staged_files: list[tuple[int, Path, Path]],
        delete_ids: set[int],
        commit_started: bool,
    ) -> bool:
        """核实失败事务的结果，只有确认未删除记录时才恢复文件。

        Args:
            staged_files: 日志 ID、原路径和暂存路径列表。
            delete_ids: 本次事务准备删除的日志 ID。
            commit_started: 是否已经调用提交，提交结果可能因断线而不确定。
        Returns:
            True 表示数据库已完成删除，可继续清理暂存文件；False 表示已回滚。
        Raises:
            DbBackupDeleteError: 结果无法确认或文件恢复失败，保留暂存文件供恢复。
        """
        try:
            # rollback 只结束本地事务状态，不能证明服务器未完成 COMMIT。
            await self.session.rollback()
            if commit_started:
                existing_ids = await self._get_existing_log_ids(delete_ids)
                if not existing_ids:
                    logger.warning(f"已确认异常提交实际完成，继续清理备份文件 log_ids={sorted(delete_ids)}")
                    return True
                if existing_ids != delete_ids:
                    raise DbBackupDeleteError("备份日志状态不一致，已保留暂存文件，请刷新列表后检查")
        except DbBackupDeleteError:
            raise
        except Exception as exc:
            logger.exception(f"无法确认备份删除事务结果 log_ids={sorted(delete_ids)}")
            raise DbBackupDeleteError(
                "暂时无法确认删除结果，已保留暂存备份文件；数据库连接恢复后请重启服务恢复检查"
            ) from exc

        restore_failures = [
            log_id
            for log_id, original_path, staged_path in staged_files
            if not self._restore_staged_file(original_path, staged_path)
        ]
        if restore_failures:
            raise DbBackupDeleteError(
                f"删除未完成，部分备份文件恢复失败，已保留暂存文件，日志 ID：{restore_failures}"
            )
        return False

    async def delete_logs(self, log_ids: list[int]) -> tuple[int, list[int], str]:
        """批量删除备份日志及其关联文件。

        Args:
            log_ids: 要删除的日志 ID 列表，重复 ID 会自动去重。
        Returns:
            (已删除的日志记录数, 未完整处理的日志 ID, 提示消息)
        """
        unique_ids = list(dict.fromkeys(log_ids))
        if not unique_ids:
            return 0, [], "请选择要删除的备份日志"
        result = await self.session.execute(
            select(DbBackupLog)
            .where(DbBackupLog.id.in_(unique_ids))
            .order_by(DbBackupLog.id.asc())
            .with_for_update()
        )
        logs = list(result.scalars().all())
        if not logs:
            return 0, unique_ids, "未找到可删除的备份日志"

        found_ids = {log.id for log in logs}
        not_found_ids = [log_id for log_id in unique_ids if log_id not in found_ids]
        unsafe_path_ids: list[int] = []
        stage_failed_ids: list[int] = []
        failed_ids = list(not_found_ids)
        staged_files: list[tuple[int, Path, Path]] = []
        logs_to_delete: list[DbBackupLog] = []
        delete_ids: set[int] = set()
        commit_started = False
        try:
            for log in logs:
                try:
                    file_path = self._locate_deletable_file(log)
                except ValueError:
                    logger.error(
                        f"拒绝删除备份目录外文件 log_id={log.id} path={log.file_path}"
                    )
                    unsafe_path_ids.append(log.id)
                    failed_ids.append(log.id)
                    continue
                if file_path:
                    try:
                        original_path, staged_path = self._stage_file_for_delete(
                            file_path, log.id
                        )
                    except OSError as exc:
                        logger.exception(
                            f"暂存备份文件失败 log_id={log.id} path={file_path}: {exc}"
                        )
                        stage_failed_ids.append(log.id)
                        failed_ids.append(log.id)
                        continue
                    staged_files.append((log.id, original_path, staged_path))
                logs_to_delete.append(log)

            # 回滚会使 ORM 属性过期，补偿过程中仅使用提前保存的标量 ID。
            delete_ids = {log.id for log in logs_to_delete}
            for log in logs_to_delete:
                await self.session.delete(log)
            if logs_to_delete:
                commit_started = True
                await self.session.commit()
        except (Exception, asyncio.CancelledError) as exc:
            logger.opt(exception=exc).error(
                f"删除备份日志事务异常，开始核实并恢复 log_ids={unique_ids}"
            )
            try:
                committed = await self._recover_failed_delete(staged_files, delete_ids, commit_started)
            except Exception:
                if isinstance(exc, asyncio.CancelledError):
                    logger.exception("删除任务取消后的恢复未完成，保留暂存文件")
                    raise exc
                raise
            if isinstance(exc, asyncio.CancelledError):
                if committed:
                    for log_id, _, staged_path in staged_files:
                        self._remove_staged_file(staged_path, log_id)
                raise
            if not committed:
                raise DbBackupDeleteError("删除备份日志失败，关联备份文件已保留，请稍后重试") from exc

        deleted = len(logs_to_delete)
        cleanup_failed_ids = [
            log_id
            for log_id, _, staged_path in staged_files
            if not self._remove_staged_file(staged_path, log_id)
        ]
        failed_ids = list(dict.fromkeys([*failed_ids, *cleanup_failed_ids]))
        if failed_ids:
            issues: list[str] = []
            if not_found_ids:
                issues.append(f"未找到或已删除的日志 ID：{not_found_ids}")
            if unsafe_path_ids:
                issues.append(f"备份文件不在当前备份目录的日志 ID：{unsafe_path_ids}")
            if stage_failed_ids:
                issues.append(f"备份文件暂存失败的日志 ID：{stage_failed_ids}")
            if cleanup_failed_ids:
                issues.append(
                    f"日志记录已删除但关联文件清理失败的日志 ID：{cleanup_failed_ids}"
                )
            return deleted, failed_ids, f"已删除 {deleted} 条日志记录；" + "；".join(issues)
        return deleted, [], f"成功删除 {deleted} 条备份日志"
