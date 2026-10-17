"""
数据库备份日志查询服务

功能：
1. 数据库备份日志分页查询（按状态、时间范围筛选）
2. 根据日志ID获取备份文件路径，用于下载
3. 删除备份日志及其关联的备份文件
4. 仅管理员可访问（鉴权在路由层处理）
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.db_backup_log import DbBackupLog
from common.utils.backup_paths import locate_backup_file
from common.utils.pagination import execute_paginated_with_filters
from common.utils.time_utils import safe_isoformat


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
            filters.append(DbBackupLog.status == status)

        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                filters.append(DbBackupLog.created_at >= start_dt)
            except ValueError:
                pass

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
                filters.append(DbBackupLog.created_at <= end_dt)
            except ValueError:
                pass

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

    async def get_backup_file(self, log_id: int) -> tuple[Optional[Path], Optional[str]]:
        """根据日志ID解析可下载的备份文件路径。

        Returns:
            (文件路径, 文件名)；当日志不存在或文件不可用时返回 (None, None)。
        """
        result = await self.session.execute(
            select(DbBackupLog).where(DbBackupLog.id == log_id)
        )
        log = result.scalar_one_or_none()
        if not log or not log.file_name:
            return None, None

        file_path = locate_backup_file(log.file_name, log.file_path)
        if not file_path:
            return None, None
        return file_path, log.file_name

    async def delete_log(self, log_id: int) -> tuple[bool, str]:
        """删除备份日志及其关联的备份文件。

        文件不存在（如失败记录）时仅删除日志记录；
        文件删除失败（权限等）时中止并返回失败，避免出现文件残留。

        Returns:
            (是否成功, 提示消息)
        """
        result = await self.session.execute(
            select(DbBackupLog).where(DbBackupLog.id == log_id)
        )
        log = result.scalar_one_or_none()
        if not log:
            return False, "备份日志不存在或已被删除"

        file_path = locate_backup_file(log.file_name, log.file_path)
        if file_path:
            try:
                # missing_ok：容忍定位与删除之间文件被移除的极端情况
                file_path.unlink(missing_ok=True)
            except OSError:
                return False, "备份文件删除失败，请检查文件权限"

        await self.session.delete(log)
        await self.session.commit()
        return True, "备份日志已删除"
