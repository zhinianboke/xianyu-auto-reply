"""
数据库备份日志查询、下载与删除路由

功能：
1. 仅管理员可查询数据库备份日志（按状态、时间范围筛选 + 分页）
2. 仅管理员可下载指定的备份文件
3. 仅管理员可删除备份日志及其关联的备份文件
4. 与前端「日志管理 / 数据库备份日志」页面对接
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from app.api import deps
from app.services.db_backup_log_service import DbBackupDeleteError, DbBackupLogService
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
        return {
            "success": True,
            "code": 200,
            "message": "查询成功",
            "data": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except ValueError as exc:
        logger.warning(
            f"查询数据库备份日志参数错误 status={status} start_date={start_date} "
            f"end_date={end_date}: {exc}"
        )
        return {
            "success": False,
            "code": 40001,
            "message": str(exc),
            "data": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        }
    except Exception as exc:
        logger.exception(
            f"查询数据库备份日志异常 status={status} start_date={start_date} "
            f"end_date={end_date}: {exc}"
        )
        return {
            "success": False,
            "code": 50001,
            "message": "加载数据库备份日志失败，请稍后重试",
            "data": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        }


@router.get("/db-backup-logs/{log_id}/download")
async def download_db_backup_file(
    log_id: int = Path(..., ge=1, le=2**63 - 1, description="备份日志 ID"),
    _: User = Depends(deps.get_current_admin_user),
    backup_log_service: DbBackupLogService = Depends(deps.get_db_backup_log_service),
):
    """下载指定备份日志对应的备份文件（仅管理员）。

    文件不存在时返回统一的错误结构（HTTP 200 + success=False），由前端弹窗提示。
    """
    try:
        file_path, file_name = await backup_log_service.get_backup_file(log_id)
    except Exception as exc:
        logger.exception(f"查询待下载备份文件异常 log_id={log_id}: {exc}")
        return {
            "success": False,
            "code": 50001,
            "message": "获取备份文件失败，请稍后重试",
            "data": None,
        }
    if not file_path or not file_name:
        return {
            "success": False,
            "code": 40004,
            "message": "备份文件不存在或已被删除，无法下载",
            "data": None,
        }

    try:
        # 在构造响应前打开文件，避免定位成功后到真正开始流式读取之间被并发删除。
        file_handle = file_path.open("rb")
    except OSError as exc:
        logger.exception(f"打开备份文件失败 log_id={log_id} path={file_path}: {exc}")
        return {
            "success": False,
            "code": 40004,
            "message": "备份文件不存在或无法读取，无法下载",
            "data": None,
        }

    # 使用 StreamingResponse 分块读取发送，避免大文件一次性载入内存或下载卡住
    def iter_file():
        with file_handle:
            while chunk := file_handle.read(64 * 1024):
                yield chunk

    # 文件名按 RFC 5987 编码，兼容中文/特殊字符
    disposition = f"attachment; filename*=UTF-8''{quote(file_name)}"
    return StreamingResponse(
        iter_file(),
        media_type="application/gzip",
        headers={"Content-Disposition": disposition},
    )


@router.delete("/db-backup-logs/{log_id}")
async def delete_db_backup_log(
    log_id: int = Path(..., ge=1, le=2**63 - 1, description="备份日志 ID"),
    current_user: User = Depends(deps.get_current_admin_user),
    backup_log_service: DbBackupLogService = Depends(deps.get_db_backup_log_service),
) -> dict:
    """删除指定的备份日志及其关联的备份文件（仅管理员）。

    返回统一的 success/message 结构，由前端弹窗提示。
    """
    operator_id = current_user.id
    try:
        success, message, code = await backup_log_service.delete_log(log_id)
        logger.info(
            f"删除备份日志完成 operator_id={operator_id} log_id={log_id} "
            f"success={success} code={code} message={message}"
        )
        return {
            "success": success,
            "code": code,
            "message": message,
            "data": None,
        }
    except Exception as exc:
        logger.exception(f"删除备份日志异常 operator_id={operator_id} log_id={log_id}: {exc}")
        # 删除失败也按统一业务响应返回，避免数据库异常直接变成 HTTP 500。
        return {
            "success": False,
            "code": 50001,
            "message": str(exc) if isinstance(exc, DbBackupDeleteError) else "删除备份日志失败，请稍后重试",
            "data": None,
        }


@router.post("/db-backup-logs/batch-delete")
async def batch_delete_db_backup_logs(
    request: Request,
    current_user: User = Depends(deps.get_current_admin_user),
    backup_log_service: DbBackupLogService = Depends(deps.get_db_backup_log_service),
) -> dict:
    """批量删除备份日志及关联文件（仅管理员）。"""
    operator_id = current_user.id
    try:
        try:
            payload = await request.json()
        except ValueError:
            return {
                "success": False,
                "code": 40001,
                "message": "请求数据格式不正确",
                "data": None,
            }
        log_ids = payload.get("ids") if isinstance(payload, dict) else None
        if not isinstance(log_ids, list) or not log_ids:
            return {
                "success": False,
                "code": 40001,
                "message": "请选择要删除的备份日志",
                "data": None,
            }
        if len(log_ids) > 100:
            return {
                "success": False,
                "code": 40001,
                "message": "单次最多删除 100 条备份日志",
                "data": None,
            }
        if any(
            not isinstance(log_id, int)
            or isinstance(log_id, bool)
            or log_id <= 0
            or log_id > 2**63 - 1
            for log_id in log_ids
        ):
            return {
                "success": False,
                "code": 40001,
                "message": "备份日志 ID 格式不正确",
                "data": None,
            }

        deleted, failed_ids, message = await backup_log_service.delete_logs(log_ids)
        success = deleted > 0 and not failed_ids
        code = 200 if success else 40002 if deleted > 0 else 40001
        logger.info(
            f"批量删除备份日志完成 operator_id={operator_id} requested_ids={log_ids} "
            f"deleted={deleted} failed_ids={failed_ids} code={code} message={message}"
        )
        return {
            "success": success,
            "code": code,
            "message": message,
            "data": {"deleted": deleted} if success else None,
        }
    except Exception as exc:
        logger.exception(
            f"批量删除备份日志异常 operator_id={operator_id}: {exc}"
        )
        return {
            "success": False,
            "code": 50001,
            "message": str(exc) if isinstance(exc, DbBackupDeleteError) else "批量删除备份日志失败，请稍后重试",
            "data": None,
        }
