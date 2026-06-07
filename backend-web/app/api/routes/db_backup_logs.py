"""
数据库备份日志查询与下载路由

功能：
1. 仅管理员可查询数据库备份日志（按状态、时间范围筛选 + 分页）
2. 仅管理员可下载指定的备份文件
3. 与前端「日志管理 / 数据库备份日志」页面对接
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from urllib.parse import quote

from app.api import deps
from app.services.db_backup_log_service import DbBackupLogService
from common.models.user import User

router = APIRouter(tags=["数据库备份日志"])


@router.get("/db-backup-logs")
async def list_db_backup_logs(
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    status: str | None = Query(default=None, description="备份状态 success/failed"),
    start_date: str | None = Query(default=None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期 YYYY-MM-DD"),
    _: User = Depends(deps.get_current_admin_user),
    backup_log_service: DbBackupLogService = Depends(deps.get_db_backup_log_service),
) -> dict:
    """分页查询数据库备份日志（仅管理员）。

    返回统一结构：success/data/total/limit/offset，异常通过 success=False + message 返回。
    """
    try:
        items, total = await backup_log_service.list_logs(
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        return {"success": True, "data": items, "total": total, "limit": limit, "offset": offset}
    except Exception as exc:
        return {
            "success": False,
            "message": f"加载数据库备份日志失败: {str(exc)}",
            "data": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        }


@router.get("/db-backup-logs/{log_id}/download")
async def download_db_backup_file(
    log_id: int,
    _: User = Depends(deps.get_current_admin_user),
    backup_log_service: DbBackupLogService = Depends(deps.get_db_backup_log_service),
):
    """下载指定备份日志对应的备份文件（仅管理员）。

    文件不存在时返回统一的错误结构（HTTP 200 + success=False），由前端弹窗提示。
    """
    file_path, file_name = await backup_log_service.get_backup_file(log_id)
    if not file_path or not file_name:
        return {
            "success": False,
            "message": "备份文件不存在或已被删除，无法下载",
            "data": None,
        }

    # 使用 StreamingResponse 分块读取发送，避免大文件一次性载入内存或下载卡住
    def iter_file():
        with file_path.open("rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk

    # 文件名按 RFC 5987 编码，兼容中文/特殊字符
    disposition = f"attachment; filename*=UTF-8''{quote(file_name)}"
    return StreamingResponse(
        iter_file(),
        media_type="application/gzip",
        headers={"Content-Disposition": disposition},
    )
