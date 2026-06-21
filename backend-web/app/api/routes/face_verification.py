"""
人脸验证管理路由模块

提供人脸验证相关的管理接口，包括：
- 查询验证通知
- 查询特定账号的验证信息
- 获取和删除验证截图
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path
import os

from app.api.deps import get_db_session as get_db, get_current_active_user
from common.models import User, UserRole
from common.models.message_notification import MessageNotification as Notification
from common.models.xy_account import XYAccount as Cookie
from common.schemas.common import ApiResponse
from loguru import logger

from common.utils.time_utils import safe_isoformat
router = APIRouter(prefix="/face-verification", tags=["人脸验证管理"])


def _is_admin(user: User) -> bool:
    """判断用户是否为管理员。"""
    return user.role == UserRole.ADMIN


@router.get("/notifications")
async def get_face_verification_notifications(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    account_id: Optional[int] = Query(None, description="账号ID筛选"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ApiResponse:
    """
    查询人脸验证通知列表
    
    Args:
        page: 页码
        page_size: 每页数量
        account_id: 账号ID筛选（可选）
        start_date: 开始日期（可选）
        end_date: 结束日期（可选）
        db: 数据库会话
        
    Returns:
        ApiResponse: 包含通知列表和分页信息
    """
    try:
        # 构建查询条件
        conditions = [
            Notification.type == "face_verification"
        ]

        # 非管理员仅能查看自己名下账号的人脸验证通知
        if not _is_admin(current_user):
            owned_result = await db.execute(
                select(Cookie.id).where(Cookie.owner_id == current_user.id)
            )
            owned_account_ids = [row[0] for row in owned_result.all()]
            if not owned_account_ids:
                return ApiResponse(
                    success=True,
                    message="查询成功",
                    data={
                        "list": [],
                        "total": 0,
                        "page": page,
                        "page_size": page_size,
                        "total_pages": 0
                    }
                )
            conditions.append(Notification.cookie_id.in_(owned_account_ids))

        if account_id:
            conditions.append(Notification.cookie_id == account_id)
        
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                conditions.append(Notification.created_at >= start_dt)
            except ValueError:
                return ApiResponse(
                    success=False,
                    message="开始日期格式错误，应为 YYYY-MM-DD",
                    data=None
                )
        
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                conditions.append(Notification.created_at < end_dt)
            except ValueError:
                return ApiResponse(
                    success=False,
                    message="结束日期格式错误，应为 YYYY-MM-DD",
                    data=None
                )
        
        # 查询总数
        count_query = select(Notification).where(and_(*conditions))
        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())
        
        # 查询分页数据
        offset = (page - 1) * page_size
        query = (
            select(Notification)
            .where(and_(*conditions))
            .order_by(desc(Notification.created_at))
            .offset(offset)
            .limit(page_size)
        )
        
        result = await db.execute(query)
        notifications = result.scalars().all()
        
        # 获取账号信息
        account_ids = list(set([n.cookie_id for n in notifications if n.cookie_id]))
        accounts_dict = {}
        if account_ids:
            accounts_result = await db.execute(
                select(Cookie).where(Cookie.id.in_(account_ids))
            )
            accounts = accounts_result.scalars().all()
            accounts_dict = {acc.id: acc.username for acc in accounts}
        
        # 构建返回数据
        notification_list = []
        for notification in notifications:
            notification_list.append({
                "id": notification.id,
                "account_id": notification.cookie_id,
                "account_name": accounts_dict.get(notification.cookie_id, "未知账号"),
                "title": notification.title,
                "content": notification.content,
                "type": notification.type,
                "is_read": notification.is_read,
                "created_at": safe_isoformat(notification.created_at),
                "extra_data": notification.extra_data
            })
        
        return ApiResponse(
            success=True,
            message="查询成功",
            data={
                "list": notification_list,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"查询失败: {str(e)}",
            data=None
        )


@router.get("/notifications/{account_id}")
async def get_account_face_verification(
    account_id: int,
    limit: int = Query(10, ge=1, le=100, description="返回数量限制"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ApiResponse:
    """
    查询特定账号的人脸验证通知
    
    Args:
        account_id: 账号ID
        limit: 返回数量限制
        db: 数据库会话
        
    Returns:
        ApiResponse: 包含该账号的验证通知列表
    """
    try:
        # 查询账号信息
        account_result = await db.execute(
            select(Cookie).where(Cookie.id == account_id)
        )
        account = account_result.scalar_one_or_none()
        
        if not account:
            return ApiResponse(
                success=False,
                message="账号不存在",
                data=None
            )

        # 账号归属校验：非管理员只能查看自己名下账号
        if not _is_admin(current_user) and account.owner_id != current_user.id:
            return ApiResponse(
                success=False,
                message="无权查看该账号",
                data=None
            )
        
        # 查询该账号的人脸验证通知
        query = (
            select(Notification)
            .where(
                and_(
                    Notification.cookie_id == account_id,
                    Notification.type == "face_verification"
                )
            )
            .order_by(desc(Notification.created_at))
            .limit(limit)
        )
        
        result = await db.execute(query)
        notifications = result.scalars().all()
        
        # 构建返回数据
        notification_list = []
        for notification in notifications:
            notification_list.append({
                "id": notification.id,
                "title": notification.title,
                "content": notification.content,
                "type": notification.type,
                "is_read": notification.is_read,
                "created_at": safe_isoformat(notification.created_at),
                "extra_data": notification.extra_data
            })
        
        return ApiResponse(
            success=True,
            message="查询成功",
            data={
                "account_id": account_id,
                "account_name": account.username,
                "notifications": notification_list,
                "total": len(notification_list)
            }
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"查询失败: {str(e)}",
            data=None
        )


@router.post("/notifications/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ApiResponse:
    """
    标记通知为已读
    
    Args:
        notification_id: 通知ID
        db: 数据库会话
        
    Returns:
        ApiResponse: 操作结果
    """
    try:
        # 查询通知
        result = await db.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        notification = result.scalar_one_or_none()
        
        if not notification:
            return ApiResponse(
                success=False,
                message="通知不存在",
                data=None
            )

        # 归属校验：非管理员只能操作自己名下账号的通知
        if not _is_admin(current_user):
            account_result = await db.execute(
                select(Cookie).where(Cookie.id == notification.cookie_id)
            )
            account = account_result.scalar_one_or_none()
            if not account or account.owner_id != current_user.id:
                return ApiResponse(
                    success=False,
                    message="无权操作该通知",
                    data=None
                )
        
        # 标记为已读
        notification.is_read = True
        await db.commit()
        
        return ApiResponse(
            success=True,
            message="标记成功",
            data={
                "notification_id": notification_id
            }
        )
        
    except Exception as e:
        await db.rollback()
        return ApiResponse(
            success=False,
            message=f"标记失败: {str(e)}",
            data=None
        )



@router.get("/screenshot/{account_id}")
async def get_face_verification_screenshot(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ApiResponse:
    """
    获取账号的人脸验证截图
    
    Args:
        account_id: 账号ID
        db: 数据库会话
        
    Returns:
        ApiResponse: 包含截图信息
    """
    try:
        # 查询账号信息
        account_result = await db.execute(
            select(Cookie).where(Cookie.account_id == account_id)
        )
        account = account_result.scalar_one_or_none()
        
        if not account:
            return ApiResponse(
                success=False,
                message="账号不存在",
                data=None
            )

        # 账号归属校验：非管理员只能读取自己名下账号的截图（含人脸隐私）
        if not _is_admin(current_user) and account.owner_id != current_user.id:
            return ApiResponse(
                success=False,
                message="无权查看该账号截图",
                data=None
            )
        
        # 查找截图文件 - 使用统一的静态文件根目录（兼容Docker共享卷）
        from app.core.paths import STATIC_ROOT
        screenshot_dir = STATIC_ROOT / "uploads" / "face"
        
        # 查找该账号的所有截图（可能有多个带时间戳的）
        import glob
        pattern = str(screenshot_dir / f"face_verify_{account_id}_*.jpg")
        screenshot_files = glob.glob(pattern)
        
        if not screenshot_files:
            return ApiResponse(
                success=False,
                message="未找到验证截图",
                data=None
            )
        
        # 获取最新的截图（按修改时间排序）
        screenshot_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        screenshot_path = Path(screenshot_files[0])
        screenshot_filename = screenshot_path.name
        
        # 获取文件信息
        file_stat = screenshot_path.stat()
        created_time = file_stat.st_ctime
        created_time_dt = datetime.fromtimestamp(created_time)
        
        # 构建返回数据
        screenshot_data = {
            "filename": screenshot_filename,
            "account_id": account_id,
            "path": f"/static/uploads/face/{screenshot_filename}",
            "size": file_stat.st_size,
            "created_time": created_time,
            "created_time_str": created_time_dt.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        return ApiResponse(
            success=True,
            message="获取成功",
            data={
                "screenshot": screenshot_data
            }
        )
        
    except Exception as e:
        logger.error(f"获取人脸验证截图失败: {account_id}, 错误: {str(e)}")
        return ApiResponse(
            success=False,
            message=f"获取失败: {str(e)}",
            data=None
        )


@router.delete("/screenshot/{account_id}")
async def delete_face_verification_screenshot(
    account_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ApiResponse:
    """
    删除账号的人脸验证截图
    
    Args:
        account_id: 账号ID
        db: 数据库会话
        
    Returns:
        ApiResponse: 删除结果
    """
    try:
        # 查询账号信息
        account_result = await db.execute(
            select(Cookie).where(Cookie.account_id == account_id)
        )
        account = account_result.scalar_one_or_none()
        
        if not account:
            return ApiResponse(
                success=False,
                message="账号不存在",
                data=None
            )

        # 账号归属校验：非管理员只能删除自己名下账号的截图
        if not _is_admin(current_user) and account.owner_id != current_user.id:
            return ApiResponse(
                success=False,
                message="无权删除该账号截图",
                data=None
            )
        
        # 查找并删除截图文件 - 使用统一的静态文件根目录（兼容Docker共享卷）
        from app.core.paths import STATIC_ROOT
        screenshot_dir = STATIC_ROOT / "uploads" / "face"
        
        # 查找该账号的所有截图
        import glob
        pattern = str(screenshot_dir / f"face_verify_{account_id}_*.jpg")
        screenshot_files = glob.glob(pattern)
        
        deleted_count = 0
        for screenshot_file in screenshot_files:
            try:
                os.remove(screenshot_file)
                deleted_count += 1
                logger.info(f"已删除人脸验证截图: {screenshot_file}")
            except Exception as e:
                logger.error(f"删除截图文件失败: {screenshot_file}, 错误: {str(e)}")
        
        return ApiResponse(
            success=True,
            message=f"删除成功，共删除 {deleted_count} 个截图" if deleted_count > 0 else "未找到截图文件",
            data={
                "deleted_count": deleted_count
            }
        )
        
    except Exception as e:
        logger.error(f"删除人脸验证截图失败: {account_id}, 错误: {str(e)}")
        return ApiResponse(
            success=False,
            message=f"删除失败: {str(e)}",
            data=None
        )
