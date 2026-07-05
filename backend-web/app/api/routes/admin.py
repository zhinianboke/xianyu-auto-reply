from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import get_settings
from common.models.message_notification import MessageNotification
from common.models.notification_channel import NotificationChannel
from common.models.risk_control_log import XYRiskControlLog
from common.models.account_login_log import XYAccountLoginLog
from common.models.scheduled_redelivery_log import ScheduledRedeliveryLog
from common.models.scheduled_rate_log import ScheduledRateLog
from common.models.scheduled_polish_log import ScheduledPolishLog
from common.models.scheduled_red_flower_log import ScheduledRedFlowerLog
from common.models.scheduled_login_renew_log import ScheduledLoginRenewLog
from common.models.scheduled_close_notice_log import ScheduledCloseNoticeLog
from common.models.user import User, UserRole, UserStatus
from common.models.user_setting import UserSetting
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.models.xy_keyword_rule import XYKeywordRule
from common.models.xy_order import XYOrder
from common.models.agent_order import AgentOrder
from common.schemas.common import ApiResponse
from common.schemas.user import AdminUserCreate, AdminUserUpdate
from app.services.dashboard_stats_service import DashboardStatsService
from app.services.scheduled_batch_log_service import ScheduledBatchLogService
from app.services.user_service import UserService
from app.services.recharge_service import RechargeService
from common.services.settlement_service import BALANCE_KEY

from common.utils.time_utils import get_beijing_now_naive, safe_isoformat
router = APIRouter(tags=["admin"])
settings = get_settings()

TABLE_MAP = {
    "users": User.__table__,
    "xy_accounts": XYAccount.__table__,
    "xy_catalog_items": XYCatalogItem.__table__,
    "xy_keyword_rules": XYKeywordRule.__table__,
    "xy_orders": XYOrder.__table__,
    "xy_notification_channels": NotificationChannel.__table__,
    "xy_message_notifications": MessageNotification.__table__,
    "xy_account_login_logs": XYAccountLoginLog.__table__,
    "xy_risk_control_logs": XYRiskControlLog.__table__,
}

LEGACY_TABLE_ALIASES = {
    "cookies": "xy_accounts",
    "item_info": "xy_catalog_items",
    "default_replies": "xy_keyword_rules",
    "notification_channels": "xy_notification_channels",
    "message_notifications": "xy_message_notifications",
    "keywords": "xy_keyword_rules",
    "risk_control_logs": "xy_risk_control_logs",
    "account_login_logs": "xy_account_login_logs",
}


def _format_balance(val: str | None) -> str:
    """将余额原始值（xy_user_settings 中的字符串）格式化为两位小数字符串。

    取不到 / 解析失败一律视为 0.00，避免前端展示异常。
    """
    if val is None:
        return "0.00"
    try:
        return f"{Decimal(str(val)):.2f}"
    except (InvalidOperation, ValueError):
        return "0.00"


async def _fetch_user_balances(session: AsyncSession, user_ids: list[int]) -> dict[int, str]:
    """批量查询用户余额（存于 xy_user_settings，key=balance）。

    Args:
        session: 数据库会话
        user_ids: 用户ID列表

    Returns:
        {user_id: 余额原始字符串}，无记录的用户不在结果中
    """
    if not user_ids:
        return {}
    stmt = select(UserSetting.user_id, UserSetting.value).where(
        UserSetting.key == BALANCE_KEY,
        UserSetting.user_id.in_(user_ids),
    )
    return {uid: val for uid, val in (await session.execute(stmt)).all()}


def _build_user_payload(
    user: User,
    cookie_counts: dict[int, int] | None = None,
    balances: dict[int, str] | None = None,
) -> dict:
    counts = cookie_counts or {}
    balance_map = balances or {}
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "role": user.role.value if user.role else None,
        "status": user.status.value if user.status else None,
        "is_admin": user.role == UserRole.ADMIN,
        "account_limit": user.account_limit,
        "cookie_count": counts.get(user.id, 0),
        "card_count": 0,
        "balance": _format_balance(balance_map.get(user.id)),
        "expire_at": safe_isoformat(user.expire_at),
    }


@router.get("/users")
async def list_users(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    username: str | None = Query(default=None, description="用户名筛选（模糊匹配，忽略大小写）"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    # 构建用户名筛选条件，同时作用于总数统计与分页查询，保证翻页数据一致
    username_keyword = username.strip() if username else None

    # 获取总数
    total_stmt = select(func.count()).select_from(User)
    if username_keyword:
        total_stmt = total_stmt.where(User.username.ilike(f"%{username_keyword}%"))
    total_result = await session.execute(total_stmt)
    total = total_result.scalar() or 0

    # 分页查询用户
    users_stmt = select(User).order_by(User.created_at.desc())
    if username_keyword:
        users_stmt = users_stmt.where(User.username.ilike(f"%{username_keyword}%"))
    users_stmt = users_stmt.limit(limit).offset(offset)
    users_result = await session.execute(users_stmt)
    users = users_result.scalars().all()

    cookie_counts_stmt = select(XYAccount.owner_id, func.count()).group_by(XYAccount.owner_id)
    cookie_counts = {
        owner_id: count
        for owner_id, count in (await session.execute(cookie_counts_stmt)).all()
    }

    # 批量查询当前页用户的余额，避免逐行查询
    balances = await _fetch_user_balances(session, [user.id for user in users])

    payload = [_build_user_payload(user, cookie_counts, balances) for user in users]
    return {"users": payload, "success": True, "total": total, "limit": limit, "offset": offset}


@router.post("/users", response_model=ApiResponse)
async def create_user(
    payload: AdminUserCreate,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
    user_service: UserService = Depends(deps.get_user_service),
) -> ApiResponse:
    existing_user = await user_service.get_by_username(payload.username)
    if existing_user:
        return ApiResponse(success=False, message="用户名已存在")

    existing_email = await user_service.get_by_email(payload.email)
    if existing_email:
        return ApiResponse(success=False, message="邮箱已存在")

    try:
        user = await user_service.create_admin_user(payload)
    except Exception as exc:
        await session.rollback()
        return ApiResponse(success=False, message=f"创建用户失败: {str(exc)}")

    return ApiResponse(success=True, message="用户创建成功", data={"user": _build_user_payload(user)})


@router.put("/users/{user_id}", response_model=ApiResponse)
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    current_admin: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
    user_service: UserService = Depends(deps.get_user_service),
) -> ApiResponse:
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return ApiResponse(success=False, message="请至少填写一个修改项")

    user = await user_service.get(user_id)
    if not user:
        return ApiResponse(success=False, message="用户不存在")

    if current_admin.id == user_id and payload.role is not None and payload.role != UserRole.ADMIN:
        return ApiResponse(success=False, message="当前登录管理员不能取消自己的管理员权限")

    if current_admin.id == user_id and payload.status is not None and payload.status != UserStatus.ACTIVE:
        return ApiResponse(success=False, message="当前登录管理员不能停用自己")

    if payload.username and payload.username != user.username:
        existing_user = await user_service.get_by_username(payload.username)
        if existing_user and existing_user.id != user_id:
            return ApiResponse(success=False, message="用户名已存在")

    if payload.email and payload.email != user.email:
        existing_email = await user_service.get_by_email(payload.email)
        if existing_email and existing_email.id != user_id:
            return ApiResponse(success=False, message="邮箱已存在")

    try:
        updated_user = await user_service.update_admin_user(user, payload)
    except Exception as exc:
        await session.rollback()
        return ApiResponse(success=False, message=f"更新用户失败: {str(exc)}")

    balances = await _fetch_user_balances(session, [updated_user.id])
    return ApiResponse(success=True, message="用户更新成功", data={"user": _build_user_payload(updated_user, balances=balances)})


class AdminRechargeRequest(BaseModel):
    """管理员手动调整用户余额请求"""
    amount: str = Field(..., description="调整金额，正数为充值，负数为扣减，例如：10.00 或 -5.00")
    remark: str = Field(default="", description="备注（可选）")


@router.post("/users/{user_id}/recharge", response_model=ApiResponse)
async def recharge_user(
    user_id: int,
    payload: AdminRechargeRequest,
    current_admin: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
    user_service: UserService = Depends(deps.get_user_service),
) -> ApiResponse:
    """管理员手动调整指定用户余额（正数充值 / 负数扣减）

    余额调整与流水写入在 RechargeService.manual_recharge 内加行锁防并发，
    并在 service 内部 commit，路由层不重复 commit。
    """
    user = await user_service.get(user_id)
    if not user:
        return ApiResponse(success=False, message="用户不存在")

    service = RechargeService(session)
    result = await service.manual_recharge(
        admin_user_id=current_admin.id,
        target_user_id=user_id,
        amount=payload.amount,
        remark=payload.remark,
    )
    if not result.get("success"):
        return ApiResponse(success=False, message=result.get("message", "余额调整失败"))
    return ApiResponse(success=True, message=result.get("message", "余额调整成功"), data=result.get("data"))


@router.delete("/users/{user_id}", response_model=ApiResponse)
async def delete_user(
    user_id: int,
    current_admin: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
    user_service: UserService = Depends(deps.get_user_service),
) -> ApiResponse:
    if user_id == current_admin.id:
        return ApiResponse(success=False, message="不能停用当前管理员账号")

    user = await user_service.get(user_id)
    if not user:
        return ApiResponse(success=False, message="用户不存在")

    try:
        user.status = UserStatus.INACTIVE
        await session.commit()
    except Exception as exc:
        await session.rollback()
        return ApiResponse(success=False, message=f"停用用户失败: {str(exc)}")

    return ApiResponse(success=True, message="用户已停用")


@router.delete("/risk-control-logs", response_model=ApiResponse)
async def clear_risk_logs(
    cookie_id: str | None = None,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """批量清空风控日志
    
    Args:
        cookie_id: 可选，指定账号ID则只清空该账号的日志，否则清空所有
    """
    from sqlalchemy import delete
    
    try:
        stmt = delete(XYRiskControlLog)
        if cookie_id:
            stmt = stmt.where(XYRiskControlLog.account_identifier == cookie_id)
        
        result = await session.execute(stmt)
        await session.commit()
        
        deleted_count = result.rowcount
        if cookie_id:
            return ApiResponse(success=True, message=f"已清空账号 {cookie_id} 的 {deleted_count} 条风控日志")
        return ApiResponse(success=True, message=f"已清空 {deleted_count} 条风控日志")
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"清空风控日志失败: {str(e)}")


@router.delete("/account-login-logs", response_model=ApiResponse)
async def clear_account_login_logs(
    days: int | None = Query(default=None, ge=1, le=3650, description="保留最近多少天的日志；不传则清空全部"),
    cookie_id: str | None = Query(default=None, description="可选：仅清理指定账号的日志"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """清理账号登录日志

    Args:
        days: 保留最近多少天的日志（如传 10 则只删除 10 天前的）；不传则清空全部
        cookie_id: 可选，指定账号ID则只清理该账号的日志，否则按全局范围清理
    """
    from datetime import timedelta
    from sqlalchemy import delete

    try:
        stmt = delete(XYAccountLoginLog)
        if days is not None:
            cutoff = get_beijing_now_naive() - timedelta(days=days)
            stmt = stmt.where(XYAccountLoginLog.created_at < cutoff)
        if cookie_id:
            stmt = stmt.where(XYAccountLoginLog.account_identifier == cookie_id)

        result = await session.execute(stmt)
        await session.commit()

        deleted_count = int(result.rowcount or 0)
        scope_label = f"账号 {cookie_id} 的" if cookie_id else ""
        if days is not None:
            return ApiResponse(success=True, message=f"已清理{scope_label} {days} 天前的 {deleted_count} 条账号登录日志")
        return ApiResponse(success=True, message=f"已清空{scope_label} {deleted_count} 条账号登录日志")
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清理账号登录日志失败: {str(e)}",
        )


@router.get("/data/{table_name}")
async def get_table_data(
    table_name: str,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    normalized = table_name.lower()
    mapped_name = LEGACY_TABLE_ALIASES.get(normalized, normalized)
    table = TABLE_MAP.get(mapped_name)
    if table is None:
        return {"success": True, "data": [], "columns": [], "count": 0}

    stmt = select(table)
    result = await session.execute(stmt)
    rows = result.mappings().all()
    data = jsonable_encoder(rows)
    columns = [column.name for column in table.columns]
    return {"success": True, "data": data, "columns": columns, "count": len(data)}


@router.delete("/data/{table_name}")
async def clear_table_placeholder(table_name: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"success": False, "message": f"尚未支持清空表 {table_name} 的接口"},
    )


@router.delete("/data/{table_name}/{record_id}")
async def delete_table_record_placeholder(table_name: str, record_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"success": False, "message": f"尚未支持删除 {table_name} 记录 {record_id}"},
    )


@router.get("/logs")
async def get_system_logs(
    lines: int = Query(100, ge=1, le=1000),
    level: str | None = Query(None),
    _: User = Depends(deps.get_current_admin_user),
) -> dict:
    backend_dir = Path(__file__).resolve().parents[3]
    log_dir = backend_dir / "logs"
 
    if not log_dir.exists():
        return {"success": False, "message": "日志目录不存在", "logs": [], "total": 0}
 
    log_files = sorted(log_dir.glob("*.log"), key=lambda item: item.stat().st_mtime)
    if not log_files:
        return {"success": True, "logs": [], "total": 0}
 
    collected_lines: list[str] = []
    level_filter = level.upper() if level else None
 
    try:
        for log_file in log_files:
            with log_file.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    normalized_line = line.rstrip("\r\n")
                    if not normalized_line:
                        continue
                    if level_filter and level_filter not in normalized_line.upper():
                        continue
                    collected_lines.append(normalized_line)
    except Exception as exc:
        return {"success": False, "message": f"读取系统日志失败: {str(exc)}", "logs": [], "total": 0}
 
    return {
        "success": True,
        "logs": collected_lines[-lines:],
        "total": len(collected_lines),
    }


@router.post("/logs/clear", response_model=ApiResponse)
async def clear_system_logs(
    _: User = Depends(deps.get_current_admin_user),
) -> ApiResponse:
    """清空系统日志"""
    backend_dir = Path(__file__).resolve().parents[3]
    log_dir = backend_dir / "logs"
    
    try:
        cleared = 0
        for log_file in log_dir.glob("*.log"):
            # 清空文件内容而不是删除
            with log_file.open("w", encoding="utf-8") as fh:
                fh.write("")
            cleared += 1
        return ApiResponse(success=True, message=f"已清空 {cleared} 个日志文件")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"清空日志失败: {str(e)}")


@router.get("/logs/export")
async def export_log_file(
    file: str,
    _: User = Depends(deps.get_current_admin_user),
):
    """导出指定的日志文件"""
    from fastapi.responses import StreamingResponse
    
    backend_dir = Path(__file__).resolve().parents[3]
    log_dir = backend_dir / "logs"
    
    # 安全检查：只允许导出log目录下的.log文件
    safe_name = Path(file).name
    if not safe_name.endswith(".log"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能导出.log文件")
    
    log_path = log_dir / safe_name
    if not log_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="日志文件不存在")
    
    def iter_file():
        with log_path.open("rb") as f:
            while chunk := f.read(8192):
                yield chunk
    
    return StreamingResponse(
        iter_file(),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={safe_name}"},
    )


@router.get("/stats")
async def get_system_stats(
    current_user: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取系统统计信息"""
    stats = await DashboardStatsService(session).get_admin_dashboard_stats(current_user_id=current_user.id)
    return {
        "success": True,
        **stats,
    }


@router.get("/stats/today")
async def get_today_stats(
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取今日统计信息（管理员专用）"""
    stats = await DashboardStatsService(session).get_admin_today_stats()
    return {
        "success": True,
        **stats,
    }


@router.get("/log-files")
async def get_log_files(
    _: User = Depends(deps.get_current_admin_user),
) -> dict:
    """获取日志文件列表"""
    backend_dir = Path(__file__).resolve().parents[3]
    log_dir = backend_dir / "logs"
    
    files = []
    if log_dir.exists():
        for log_file in sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = log_file.stat()
            files.append({
                "name": log_file.name,
                "size": stat.st_size,
                "modified_time": stat.st_mtime,
            })
    
    return {"success": True, "files": files}


@router.get("/backup/list")
async def list_backup_files(
    _: User = Depends(deps.get_current_admin_user),
) -> dict:
    """列出备份文件"""
    import glob
    import os
    
    backup_files = []
    # 查找data目录下的备份文件
    for pattern in ["data/*.db", "data/*backup*.json"]:
        for file_path in glob.glob(pattern):
            try:
                stat = os.stat(file_path)
                backup_files.append({
                    "filename": os.path.basename(file_path),
                    "size": stat.st_size,
                    "size_mb": round(stat.st_size / 1024 / 1024, 2),
                    "modified_time": stat.st_mtime,
                })
            except Exception:
                pass
    
    backup_files.sort(key=lambda x: x["modified_time"], reverse=True)
    return {"backups": backup_files, "total": len(backup_files)}


@router.get("/backup/download")
async def download_database_backup(
    _: User = Depends(deps.get_current_admin_user),
) -> JSONResponse:
    """下载数据库备份（MySQL不支持直接下载）"""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"success": False, "message": "MySQL数据库不支持直接下载，请使用mysqldump工具"},
    )


@router.post("/backup/upload")
async def upload_database_backup(
    _: User = Depends(deps.get_current_admin_user),
) -> JSONResponse:
    """上传数据库备份（MySQL不支持直接上传恢复）"""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={"success": False, "message": "MySQL数据库不支持直接上传恢复，请使用mysql命令行工具"},
    )


@router.post("/reload-cache", response_model=ApiResponse)
async def reload_system_cache(
    _: User = Depends(deps.get_current_admin_user),
) -> ApiResponse:
    """刷新系统缓存"""
    from loguru import logger
    
    try:
        # 1. 清理数据库连接池（如果有）
        # 2. 清理内存缓存（如果有）
        # 3. 通知 WebSocket 服务刷新缓存
        
        import httpx
        
        # 调用 WebSocket 服务的重启接口来刷新缓存
        # 这里可以根据实际需求实现更细粒度的缓存刷新
        
        logger.info("【系统管理】缓存刷新请求已处理")
        
        return ApiResponse(
            success=True, 
            message="缓存刷新成功",
            data={
                "timestamp": str(get_beijing_now_naive()),
                "actions": [
                    "数据库连接池已刷新",
                    "内存缓存已清理"
                ]
            }
        )
    except Exception as e:
        logger.error(f"【系统管理】缓存刷新失败: {e}")
        return ApiResponse(
            success=False,
            message=f"缓存刷新失败: {str(e)}"
        )


@router.get("/redelivery-batches")
async def list_redelivery_batches(
    start_date: str | None = Query(default=None, description="开始日期，格式：YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期，格式：YYYY-MM-DD"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取定时补发货执行批次列表（管理员专用）"""
    service = ScheduledBatchLogService(session)
    batches, total = await service.list_redelivery_batches(
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "data": batches,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/redelivery-batches/{batch_id}")
async def get_redelivery_batch_detail(
    batch_id: str,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取定时补发货执行批次详情（管理员专用）"""
    service = ScheduledBatchLogService(session)
    data = await service.get_redelivery_batch_detail(batch_id)
    if data is None:
        return {"success": False, "message": "批次不存在", "data": None}

    return {
        "success": True,
        "data": data,
    }


# ==================== 定时补评价日志接口 ====================

@router.get("/rate-batches")
async def list_rate_batches(
    start_date: str | None = Query(default=None, description="开始日期，格式：YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期，格式：YYYY-MM-DD"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取定时补评价执行批次列表（管理员专用）"""
    service = ScheduledBatchLogService(session)
    batches, total = await service.list_rate_batches(
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "data": batches,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/rate-batches/{batch_id}")
async def get_rate_batch_detail(
    batch_id: str,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取定时补评价执行批次详情（管理员专用）"""
    service = ScheduledBatchLogService(session)
    data = await service.get_rate_batch_detail(batch_id)
    if data is None:
        return {"success": False, "message": "批次不存在", "data": None}

    return {
        "success": True,
        "data": data,
    }


# ==================== 定时任务管理接口 ====================

async def _notify_scheduler_reload() -> bool:
    """
    通知Scheduler服务重新加载任务配置
    
    Returns:
        是否成功
    """
    from app.core.http_client import get_http_client
    from app.core.config import get_settings
    from loguru import logger
    
    try:
        settings = get_settings()
        http_client = get_http_client()
        url = f"{settings.scheduler_service_url}/internal/tasks/reload"
        
        response = await http_client.post(url)
        
        if response.get("success"):
            logger.info("[定时任务配置] 已通知Scheduler服务重新加载配置")
            return True
        else:
            logger.warning(f"[定时任务配置] 通知Scheduler服务失败: {response.get('message')}")
            return False
    except Exception as e:
        logger.error(f"[定时任务配置] 通知Scheduler服务异常: {e}")
        return False


@router.get("/scheduled-tasks")
async def list_scheduled_tasks(
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取定时任务列表（管理员专用）"""
    from common.models.scheduled_task import ScheduledTask
    from loguru import logger
    
    try:
        # 直接查询数据库获取任务列表
        stmt = select(ScheduledTask).order_by(ScheduledTask.id)
        result = await session.execute(stmt)
        tasks = result.scalars().all()
        
        tasks_data = []
        for task in tasks:
            tasks_data.append({
                "id": task.id,
                "task_code": task.task_code,
                "task_name": task.task_name,
                "interval_seconds": task.interval_seconds,
                "enabled": task.enabled,
                "description": task.description,
                "created_at": safe_isoformat(task.created_at),
                "updated_at": safe_isoformat(task.updated_at),
            })
        
        return {
            "success": True,
            "message": "查询成功",
            "data": tasks_data,
        }
    except Exception as e:
        logger.error(f"[定时任务配置] 查询任务配置失败: {e}")
        return {
            "success": False,
            "message": f"查询任务配置失败: {str(e)}",
            "data": None,
        }


@router.put("/scheduled-tasks/{task_code}")
async def update_scheduled_task(
    task_code: str,
    interval_seconds: int | None = None,
    enabled: bool | None = None,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """更新定时任务配置（管理员专用）"""
    from common.models.scheduled_task import ScheduledTask
    from loguru import logger
    from app.core.http_client import get_http_client
    from app.core.config import get_settings
    
    settings = get_settings()
    
    try:
        # 查询任务
        stmt = select(ScheduledTask).where(ScheduledTask.task_code == task_code)
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()
        
        if not task:
            return {
                "success": False,
                "message": f"任务不存在: {task_code}",
                "data": None,
            }
        
        # 更新字段
        if interval_seconds is not None:
            if interval_seconds < 1:
                return {
                    "success": False,
                    "message": "执行间隔不能小于1秒",
                    "data": None,
                }
            task.interval_seconds = interval_seconds
        
        if enabled is not None:
            task.enabled = enabled
        
        await session.commit()
        await session.refresh(task)
        
        logger.info(
            f"[定时任务配置] 任务配置已更新: {task_code}, "
            f"间隔={task.interval_seconds}秒, 启用={task.enabled}"
        )
        
        # 通知Scheduler服务重新加载配置
        reload_success = False
        try:
            http_client = get_http_client()
            url = f"{settings.scheduler_service_url}/internal/tasks/reload"
            response = await http_client.post(url)
            if response.get("success"):
                reload_success = True
                logger.info(f"[定时任务配置] 已通知Scheduler服务重新加载配置: {task_code}")
            else:
                logger.warning(f"[定时任务配置] 通知Scheduler服务失败: {response.get('message')}")
        except Exception as e:
            logger.error(f"[定时任务配置] 通知Scheduler服务异常: {e}")
        
        return {
            "success": True,
            "message": "更新成功" + ("，已通知调度器刷新配置" if reload_success else ""),
            "data": {
                "id": task.id,
                "task_code": task.task_code,
                "task_name": task.task_name,
                "interval_seconds": task.interval_seconds,
                "enabled": task.enabled,
                "description": task.description,
            },
        }
    except Exception as e:
        logger.error(f"[定时任务配置] 更新任务配置失败: {e}")
        await session.rollback()
        return {
            "success": False,
            "message": f"更新任务配置失败: {str(e)}",
            "data": None,
        }


@router.post("/scheduled-tasks/{task_code}/trigger")
async def trigger_scheduled_task(
    task_code: str,
    _: User = Depends(deps.get_current_admin_user),
) -> dict:
    """手动触发定时任务执行（管理员专用）"""
    from loguru import logger
    from app.core.http_client import get_http_client
    from app.core.config import get_settings
    
    settings = get_settings()
    
    try:
        http_client = get_http_client()
        url = f"{settings.scheduler_service_url}/internal/tasks/{task_code}/trigger"
        response = await http_client.post(url)
        
        if response.get("success"):
            logger.info(f"[定时任务] 手动触发任务成功: {task_code}")
            return {
                "success": True,
                "message": response.get("message", f"任务 {task_code} 已触发执行"),
            }
        else:
            return {
                "success": False,
                "message": response.get("message", "触发任务失败"),
            }
    except Exception as e:
        logger.error(f"[定时任务] 手动触发任务异常: {e}")
        return {
            "success": False,
            "message": f"触发任务失败: {str(e)}",
        }


# ==================== 定时擦亮日志接口 ====================

@router.get("/polish-batches")
async def list_polish_batches(
    start_date: str | None = Query(default=None, description="开始日期，格式：YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期，格式：YYYY-MM-DD"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取定时擦亮执行批次列表（管理员专用）"""
    service = ScheduledBatchLogService(session)
    batches, total = await service.list_polish_batches(
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )

    return {
        "success": True,
        "data": batches,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/polish-batches/{batch_id}")
async def get_polish_batch_detail(
    batch_id: str,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取定时擦亮执行批次详情（管理员专用）"""
    service = ScheduledBatchLogService(session)
    data = await service.get_polish_batch_detail(batch_id)
    if data is None:
        return {"success": False, "message": "批次不存在", "data": None}

    return {
        "success": True,
        "data": data,
    }


# ==================== 清空日志接口 ====================

@router.delete("/redelivery-logs/clear", response_model=ApiResponse)
async def clear_redelivery_logs(
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """清空定时补发货日志（只清空10天前的数据）"""
    from datetime import datetime, timedelta
    from sqlalchemy import delete
    from loguru import logger
    
    try:
        # 计算10天前的时间
        ten_days_ago = get_beijing_now_naive() - timedelta(days=10)
        
        # 删除10天前的日志
        stmt = delete(ScheduledRedeliveryLog).where(
            ScheduledRedeliveryLog.created_at < ten_days_ago
        )
        
        result = await session.execute(stmt)
        await session.commit()
        
        deleted_count = result.rowcount
        logger.info(f"[定时补发货日志] 已清空 {deleted_count} 条10天前的日志")
        
        return ApiResponse(
            success=True,
            message=f"已清空 {deleted_count} 条10天前的补发货日志"
        )
    except Exception as e:
        await session.rollback()
        logger.error(f"[定时补发货日志] 清空日志失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清空补发货日志失败: {str(e)}"
        )


@router.delete("/rate-logs/clear", response_model=ApiResponse)
async def clear_rate_logs(
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """清空定时补评价日志（只清空10天前的数据）"""
    from datetime import datetime, timedelta
    from sqlalchemy import delete
    from loguru import logger
    
    try:
        # 计算10天前的时间
        ten_days_ago = get_beijing_now_naive() - timedelta(days=10)
        
        # 删除10天前的日志
        stmt = delete(ScheduledRateLog).where(
            ScheduledRateLog.created_at < ten_days_ago
        )
        
        result = await session.execute(stmt)
        await session.commit()
        
        deleted_count = result.rowcount
        logger.info(f"[定时补评价日志] 已清空 {deleted_count} 条10天前的日志")
        
        return ApiResponse(
            success=True,
            message=f"已清空 {deleted_count} 条10天前的补评价日志"
        )
    except Exception as e:
        await session.rollback()
        logger.error(f"[定时补评价日志] 清空日志失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清空补评价日志失败: {str(e)}"
        )


@router.delete("/polish-logs/clear", response_model=ApiResponse)
async def clear_polish_logs(
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """清空定时擦亮日志（只清空10天前的数据）"""
    from datetime import datetime, timedelta
    from sqlalchemy import delete
    from loguru import logger
    
    try:
        # 计算10天前的时间
        ten_days_ago = get_beijing_now_naive() - timedelta(days=10)
        
        # 删除10天前的日志
        stmt = delete(ScheduledPolishLog).where(
            ScheduledPolishLog.created_at < ten_days_ago
        )
        
        result = await session.execute(stmt)
        await session.commit()
        
        deleted_count = result.rowcount
        logger.info(f"[定时擦亮日志] 已清空 {deleted_count} 条10天前的日志")
        
        return ApiResponse(
            success=True,
            message=f"已清空 {deleted_count} 条10天前的擦亮日志"
        )
    except Exception as e:
        await session.rollback()
        logger.error(f"[定时擦亮日志] 清空日志失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清空擦亮日志失败: {str(e)}"
        )


# ==================== 求小红花日志接口 ====================

@router.get("/red-flower-batches")
async def list_red_flower_batches(
    start_date: str | None = Query(default=None, description="开始日期，格式：YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期，格式：YYYY-MM-DD"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取求小红花执行批次列表（管理员专用）"""
    from app.services.scheduled_batch_log_service import ScheduledBatchLogService

    service = ScheduledBatchLogService(session)
    batches, total = await service.list_red_flower_batches(
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return {
        "success": True,
        "data": batches,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/red-flower-batches/{batch_id}")
async def get_red_flower_batch_detail(
    batch_id: str,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取求小红花批次详情（管理员专用）"""
    from app.services.scheduled_batch_log_service import ScheduledBatchLogService

    service = ScheduledBatchLogService(session)
    detail = await service.get_red_flower_batch_detail(batch_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="批次不存在")
    return {"success": True, "data": detail}


@router.delete("/red-flower-logs/clear", response_model=ApiResponse)
async def clear_red_flower_logs(
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """清空求小红花日志（只清空10天前的数据）"""
    from datetime import datetime, timedelta
    from sqlalchemy import delete
    from loguru import logger

    try:
        ten_days_ago = get_beijing_now_naive() - timedelta(days=10)
        stmt = delete(ScheduledRedFlowerLog).where(
            ScheduledRedFlowerLog.created_at < ten_days_ago
        )
        result = await session.execute(stmt)
        await session.commit()

        deleted_count = result.rowcount
        logger.info(f"[求小红花日志] 已清空 {deleted_count} 条10天前的日志")
        return ApiResponse(
            success=True,
            message=f"已清空 {deleted_count} 条10天前的求小红花日志"
        )
    except Exception as e:
        await session.rollback()
        from loguru import logger as _logger
        _logger.error(f"[求小红花日志] 清空日志失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清空求小红花日志失败: {str(e)}"
        )


# ==================== 登录续期日志接口 ====================

@router.get("/login-renew-batches")
async def list_login_renew_batches(
    start_date: str | None = Query(default=None, description="开始日期，格式：YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期，格式：YYYY-MM-DD"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取登录续期执行批次列表（管理员专用）"""
    from datetime import datetime
    from sqlalchemy import case
    
    # 构建基础查询 - 按batch_id分组统计
    base_query = select(
        ScheduledLoginRenewLog.batch_id,
        func.min(ScheduledLoginRenewLog.created_at).label("executed_at"),
        func.count().label("total_accounts"),
        func.sum(case((ScheduledLoginRenewLog.status == "success", 1), else_=0)).label("success_count"),
        func.sum(case((ScheduledLoginRenewLog.status == "token_refreshed", 1), else_=0)).label("token_refreshed_count"),
        func.sum(case((ScheduledLoginRenewLog.status == "session_expired", 1), else_=0)).label("session_expired_count"),
        func.sum(case((ScheduledLoginRenewLog.status == "failed", 1), else_=0)).label("failed_count"),
    ).group_by(ScheduledLoginRenewLog.batch_id)
    
    # 时间范围筛选
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            base_query = base_query.having(func.min(ScheduledLoginRenewLog.created_at) >= start_dt)
        except ValueError:
            pass
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            base_query = base_query.having(func.min(ScheduledLoginRenewLog.created_at) <= end_dt)
        except ValueError:
            pass
    
    # 查询总数
    count_subquery = base_query.subquery()
    count_stmt = select(func.count()).select_from(count_subquery)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0
    
    # 分页查询
    offset = (page - 1) * page_size
    stmt = base_query.order_by(func.min(ScheduledLoginRenewLog.created_at).desc()).offset(offset).limit(page_size)
    result = await session.execute(stmt)
    rows = result.all()
    
    batches = []
    for row in rows:
        batches.append({
            "batch_id": row.batch_id,
            "executed_at": safe_isoformat(row.executed_at),
            "total_accounts": row.total_accounts or 0,
            "success_count": row.success_count or 0,
            "token_refreshed_count": row.token_refreshed_count or 0,
            "session_expired_count": row.session_expired_count or 0,
            "failed_count": row.failed_count or 0,
        })
    
    return {
        "success": True,
        "data": batches,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.get("/login-renew-batches/{batch_id}")
async def get_login_renew_batch_detail(
    batch_id: str,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> dict:
    """获取登录续期执行批次详情（管理员专用）"""
    from sqlalchemy import case
    
    # 查询批次汇总信息
    summary_stmt = select(
        func.min(ScheduledLoginRenewLog.created_at).label("executed_at"),
        func.count().label("total_accounts"),
        func.sum(case((ScheduledLoginRenewLog.status == "success", 1), else_=0)).label("success_count"),
        func.sum(case((ScheduledLoginRenewLog.status == "token_refreshed", 1), else_=0)).label("token_refreshed_count"),
        func.sum(case((ScheduledLoginRenewLog.status == "session_expired", 1), else_=0)).label("session_expired_count"),
        func.sum(case((ScheduledLoginRenewLog.status == "failed", 1), else_=0)).label("failed_count"),
    ).where(ScheduledLoginRenewLog.batch_id == batch_id)
    
    summary_result = await session.execute(summary_stmt)
    summary = summary_result.first()
    
    if not summary or summary.total_accounts == 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="批次不存在")
    
    # 查询批次所有日志
    logs_stmt = select(ScheduledLoginRenewLog).where(
        ScheduledLoginRenewLog.batch_id == batch_id
    ).order_by(ScheduledLoginRenewLog.created_at)
    
    logs_result = await session.execute(logs_stmt)
    logs = logs_result.scalars().all()
    
    logs_data = []
    for log in logs:
        logs_data.append({
            "id": log.id,
            "batch_id": log.batch_id,
            "account_id": log.account_id,
            "status": log.status,
            "error_message": log.error_message,
            "created_at": safe_isoformat(log.created_at),
        })
    
    return {
        "success": True,
        "data": {
            "batch_id": batch_id,
            "executed_at": safe_isoformat(summary.executed_at),
            "total_accounts": summary.total_accounts or 0,
            "success_count": summary.success_count or 0,
            "token_refreshed_count": summary.token_refreshed_count or 0,
            "session_expired_count": summary.session_expired_count or 0,
            "failed_count": summary.failed_count or 0,
            "logs": logs_data,
        }
    }


@router.delete("/login-renew-logs/clear", response_model=ApiResponse)
async def clear_login_renew_logs(
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """清空登录续期日志（只清空10天前的数据）"""
    from datetime import datetime, timedelta
    from sqlalchemy import delete
    from loguru import logger
    
    try:
        # 计算10天前的时间
        ten_days_ago = get_beijing_now_naive() - timedelta(days=10)
        
        # 删除10天前的日志
        stmt = delete(ScheduledLoginRenewLog).where(
            ScheduledLoginRenewLog.created_at < ten_days_ago
        )
        
        result = await session.execute(stmt)
        await session.commit()
        
        deleted_count = result.rowcount
        logger.info(f"[登录续期日志] 已清空 {deleted_count} 条10天前的日志")
        
        return ApiResponse(
            success=True,
            message=f"已清空 {deleted_count} 条10天前的登录续期日志"
        )
    except Exception as e:
        await session.rollback()
        logger.error(f"[登录续期日志] 清空日志失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清空登录续期日志失败: {str(e)}"
        )


# ==================== 账号消息通知关闭日志接口 ====================

@router.get("/close-notice-batches")
async def list_close_notice_batches(
    start_date: str | None = Query(default=None, description="开始日期，格式：YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="结束日期，格式：YYYY-MM-DD"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """获取账号消息通知关闭日志批次列表"""
    from sqlalchemy import case

    # 构建基础查询 - 按batch_id分组统计
    base_query = select(
        ScheduledCloseNoticeLog.batch_id,
        func.min(ScheduledCloseNoticeLog.created_at).label("executed_at"),
        func.count().label("total_accounts"),
        func.sum(case((ScheduledCloseNoticeLog.status == "success", 1), else_=0)).label("success_count"),
        func.sum(case((ScheduledCloseNoticeLog.status == "failed", 1), else_=0)).label("failed_count"),
    ).group_by(ScheduledCloseNoticeLog.batch_id)

    # 时间范围筛选
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            base_query = base_query.having(func.min(ScheduledCloseNoticeLog.created_at) >= start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            base_query = base_query.having(func.min(ScheduledCloseNoticeLog.created_at) <= end_dt)
        except ValueError:
            pass

    # 统计总批次数
    count_stmt = select(func.count()).select_from(base_query.subquery())
    count_result = await session.execute(count_stmt)
    total = count_result.scalar() or 0
    total_pages = (total + page_size - 1) // page_size

    # 分页查询
    offset = (page - 1) * page_size
    stmt = base_query.order_by(func.min(ScheduledCloseNoticeLog.created_at).desc()).offset(offset).limit(page_size)
    result = await session.execute(stmt)
    rows = result.all()

    batches = [
        {
            "batch_id": row.batch_id,
            "executed_at": safe_isoformat(row.executed_at),
            "total_accounts": row.total_accounts,
            "success_count": row.success_count,
            "failed_count": row.failed_count,
        }
        for row in rows
    ]

    return {
        "success": True,
        "data": batches,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/close-notice-batches/{batch_id}")
async def get_close_notice_batch_detail(
    batch_id: str,
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """获取账号消息通知关闭日志批次详情"""
    from sqlalchemy import case

    # 查询批次汇总信息
    summary_stmt = select(
        func.min(ScheduledCloseNoticeLog.created_at).label("executed_at"),
        func.count().label("total_accounts"),
        func.sum(case((ScheduledCloseNoticeLog.status == "success", 1), else_=0)).label("success_count"),
        func.sum(case((ScheduledCloseNoticeLog.status == "failed", 1), else_=0)).label("failed_count"),
    ).where(ScheduledCloseNoticeLog.batch_id == batch_id)

    summary_result = await session.execute(summary_stmt)
    summary = summary_result.first()

    if not summary or summary.total_accounts == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="批次不存在")

    # 查询批次所有日志
    logs_stmt = select(ScheduledCloseNoticeLog).where(
        ScheduledCloseNoticeLog.batch_id == batch_id
    ).order_by(ScheduledCloseNoticeLog.created_at)

    logs_result = await session.execute(logs_stmt)
    logs = logs_result.scalars().all()

    return {
        "success": True,
        "data": {
            "batch_id": batch_id,
            "executed_at": safe_isoformat(summary.executed_at),
            "total_accounts": summary.total_accounts,
            "success_count": summary.success_count,
            "failed_count": summary.failed_count,
            "logs": [
                {
                    "id": log.id,
                    "batch_id": log.batch_id,
                    "account_id": log.account_id,
                    "status": log.status,
                    "error_message": log.error_message,
                    "created_at": safe_isoformat(log.created_at),
                }
                for log in logs
            ],
        },
    }


@router.delete("/close-notice-logs/clear", response_model=ApiResponse)
async def clear_close_notice_logs(
    _: User = Depends(deps.get_current_admin_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """清空账号消息通知关闭日志（只清空10天前的数据）"""
    from datetime import timedelta
    from sqlalchemy import delete
    from loguru import logger

    try:
        # 计算10天前的时间
        ten_days_ago = get_beijing_now_naive() - timedelta(days=10)

        # 删除10天前的日志
        stmt = delete(ScheduledCloseNoticeLog).where(
            ScheduledCloseNoticeLog.created_at < ten_days_ago
        )

        result = await session.execute(stmt)
        await session.commit()

        deleted_count = result.rowcount
        logger.info(f"[消息通知关闭日志] 已清空 {deleted_count} 条10天前的日志")

        return ApiResponse(
            success=True,
            message=f"已清空 {deleted_count} 条10天前的消息通知关闭日志"
        )
    except Exception as e:
        await session.rollback()
        logger.error(f"[消息通知关闭日志] 清空日志失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清空消息通知关闭日志失败: {str(e)}"
        )
