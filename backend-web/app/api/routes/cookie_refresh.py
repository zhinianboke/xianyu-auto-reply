"""
Cookie 刷新管理路由模块

提供 Cookie 刷新相关的管理接口，包括：
- 查询刷新冷却状态
- 重置刷新冷却时间
- 手动触发刷新
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta
from typing import Dict, Any
from loguru import logger

from app.api.deps import get_db_session as get_db, get_current_active_user
from common.models import User, UserRole
from common.models.xy_account import XYAccount as Cookie
from common.schemas.common import ApiResponse

from common.utils.time_utils import get_beijing_now_naive, safe_isoformat
router = APIRouter(prefix="/cookie-refresh", tags=["Cookie刷新管理"])


def _is_admin(user: User) -> bool:
    """判断用户是否为管理员。"""
    return user.role == UserRole.ADMIN


@router.get("/cooldown/{account_id}")
async def get_refresh_cooldown(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ApiResponse:
    """
    查询账号的刷新冷却状态
    
    Args:
        account_id: 账号ID
        db: 数据库会话
        
    Returns:
        ApiResponse: 包含冷却状态信息
    """
    try:
        # 查询账号信息
        result = await db.execute(
            select(Cookie).where(Cookie.id == account_id)
        )
        cookie = result.scalar_one_or_none()
        
        if not cookie:
            return ApiResponse(
                success=False,
                message="账号不存在",
                data=None
            )

        # 账号归属校验：非管理员只能查看自己名下账号
        if not _is_admin(current_user) and cookie.owner_id != current_user.id:
            return ApiResponse(
                success=False,
                message="无权查看该账号",
                data=None
            )
        
        # 检查密码登录冷却（60秒）
        password_login_cooldown = False
        password_login_remaining = 0
        if cookie.last_password_login_time:
            elapsed = (get_beijing_now_naive() - cookie.last_password_login_time).total_seconds()
            if elapsed < 60:
                password_login_cooldown = True
                password_login_remaining = int(60 - elapsed)
        
        # 检查账密错误冷却（5小时）
        account_error_cooldown = False
        account_error_remaining = 0
        if cookie.last_account_error_time:
            elapsed = (get_beijing_now_naive() - cookie.last_account_error_time).total_seconds()
            if elapsed < 18000:  # 5小时 = 18000秒
                account_error_cooldown = True
                account_error_remaining = int(18000 - elapsed)
        
        return ApiResponse(
            success=True,
            message="查询成功",
            data={
                "account_id": account_id,
                "username": cookie.username,
                "password_login_cooldown": password_login_cooldown,
                "password_login_remaining_seconds": password_login_remaining,
                "account_error_cooldown": account_error_cooldown,
                "account_error_remaining_seconds": account_error_remaining,
                "last_password_login_time": safe_isoformat(cookie.last_password_login_time),
                "last_account_error_time": safe_isoformat(cookie.last_account_error_time)
            }
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"查询失败: {str(e)}",
            data=None
        )


@router.post("/cooldown/{account_id}/reset")
async def reset_refresh_cooldown(
    account_id: int,
    cooldown_type: str,  # "password_login" 或 "account_error"
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ApiResponse:
    """
    重置账号的刷新冷却时间
    
    Args:
        account_id: 账号ID
        cooldown_type: 冷却类型（password_login 或 account_error）
        db: 数据库会话
        
    Returns:
        ApiResponse: 操作结果
    """
    try:
        # 查询账号信息
        result = await db.execute(
            select(Cookie).where(Cookie.id == account_id)
        )
        cookie = result.scalar_one_or_none()
        
        if not cookie:
            return ApiResponse(
                success=False,
                message="账号不存在",
                data=None
            )

        # 账号归属校验：非管理员只能重置自己名下账号的冷却
        if not _is_admin(current_user) and cookie.owner_id != current_user.id:
            return ApiResponse(
                success=False,
                message="无权操作该账号",
                data=None
            )
        
        # 根据类型重置冷却时间
        if cooldown_type == "password_login":
            cookie.last_password_login_time = None
            message = "密码登录冷却时间已重置"
        elif cooldown_type == "account_error":
            cookie.last_account_error_time = None
            message = "账密错误冷却时间已重置"
        else:
            return ApiResponse(
                success=False,
                message="无效的冷却类型，必须是 password_login 或 account_error",
                data=None
            )
        
        await db.commit()
        
        return ApiResponse(
            success=True,
            message=message,
            data={
                "account_id": account_id,
                "cooldown_type": cooldown_type
            }
        )
        
    except Exception as e:
        await db.rollback()
        return ApiResponse(
            success=False,
            message=f"重置失败: {str(e)}",
            data=None
        )


@router.post("/trigger/{account_id}")
async def trigger_manual_refresh(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ApiResponse:
    """
    手动触发账号的 Cookie 刷新
    
    注意：此接口仅触发刷新请求，实际刷新由 WebSocket 服务执行
    
    Args:
        account_id: 账号ID
        db: 数据库会话
        
    Returns:
        ApiResponse: 操作结果
    """
    try:
        # 查询账号信息
        result = await db.execute(
            select(Cookie).where(Cookie.id == account_id)
        )
        cookie = result.scalar_one_or_none()
        
        if not cookie:
            return ApiResponse(
                success=False,
                message="账号不存在",
                data=None
            )

        # 账号归属校验：非管理员只能触发自己名下账号的刷新
        if not _is_admin(current_user) and cookie.owner_id != current_user.id:
            return ApiResponse(
                success=False,
                message="无权操作该账号",
                data=None
            )
        
        # 检查是否在冷却期
        if cookie.last_password_login_time:
            elapsed = (get_beijing_now_naive() - cookie.last_password_login_time).total_seconds()
            if elapsed < 60:
                return ApiResponse(
                    success=False,
                    message=f"密码登录冷却中，请等待 {int(60 - elapsed)} 秒后再试",
                    data=None
                )
        
        if cookie.last_account_error_time:
            elapsed = (get_beijing_now_naive() - cookie.last_account_error_time).total_seconds()
            if elapsed < 18000:
                remaining_hours = int((18000 - elapsed) / 3600)
                remaining_minutes = int(((18000 - elapsed) % 3600) / 60)
                return ApiResponse(
                    success=False,
                    message=f"账密错误冷却中，请等待 {remaining_hours} 小时 {remaining_minutes} 分钟后再试",
                    data=None
                )
        
        # 调用 WebSocket 服务触发实际的刷新操作
        try:
            import httpx
            from app.core.config import get_settings
            
            settings = get_settings()
            websocket_url = f"{settings.WEBSOCKET_SERVICE_URL}/internal/accounts/{account_id}/refresh-token"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(websocket_url)
                
                if response.status_code == 200:
                    logger.info(f"【Cookie刷新】成功触发WebSocket服务刷新: account_id={account_id}")
                elif response.status_code == 404:
                    logger.warning(f"【Cookie刷新】账号未启动: account_id={account_id}")
                    return ApiResponse(
                        success=False,
                        message="账号未启动，请先启动账号后再刷新",
                        data=None
                    )
                else:
                    logger.error(f"【Cookie刷新】WebSocket服务返回错误: {response.status_code}")
        except Exception as e:
            logger.error(f"【Cookie刷新】调用WebSocket服务失败: {e}")
            # 即使调用失败，也返回成功，因为WebSocket服务会自动刷新
        
        return ApiResponse(
            success=True,
            message="刷新请求已提交，请等待 WebSocket 服务处理",
            data={
                "account_id": account_id,
                "username": cookie.username
            }
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            message=f"触发刷新失败: {str(e)}",
            data=None
        )
