"""
密码登录代理路由 - Backend-Web服务

功能：
1. 代理密码登录请求到WebSocket服务
2. 代理登录状态查询到WebSocket服务
3. 代理取消登录请求到WebSocket服务

密码登录需要浏览器支持，实际实现在WebSocket服务中
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel

from app.api import deps
from app.core.config import get_settings
from app.services.account_service import AccountService
from common.models.user import User
from common.services.account_limit_service import AccountLimitExceededError, AccountLimitService

router = APIRouter(prefix="/password-login", tags=["密码登录"])

settings = get_settings()


# ==================== 请求/响应模型 ====================

class PasswordLoginRequest(BaseModel):
    """密码登录请求"""
    account_id: str
    account: str
    password: str
    show_browser: bool = False


# ==================== 路由 ====================

@router.post("")
async def password_login(
    request: PasswordLoginRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """
    账号密码登录接口
    
    代理请求到WebSocket服务执行实际登录
    密码登录强制使用有头模式
    """
    try:
        if not request.account_id or not request.account or not request.password:
            return {
                "success": False,
                "message": "账号ID、登录账号和密码不能为空"
            }

        existing_account = await account_service.get_account_for_user(current_user.id, request.account_id)
        if not existing_account:
            try:
                await AccountLimitService(account_service.session).ensure_can_add_account(current_user.id)
            except AccountLimitExceededError as exc:
                return {
                    "success": False,
                    "message": str(exc)
                }
        
        logger.info(f"【{current_user.username}】开始账号密码登录: {request.account_id}")
        
        # 密码登录强制使用有头模式
        show_browser = True
        if not request.show_browser:
            logger.info(f"【{request.account_id}】密码登录强制使用有头模式")
        
        # 构建请求数据，添加user_id
        request_data = {
            "account_id": request.account_id,
            "account": request.account,
            "password": request.password,
            "show_browser": show_browser,
            "user_id": current_user.id
        }
        
        # 调用WebSocket服务
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.websocket_service_url}/password-login",
                json=request_data
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"WebSocket服务返回错误: {response.status_code}")
                return {
                    "success": False,
                    "message": f"登录服务异常: {response.status_code}"
                }
                
    except httpx.ConnectError:
        logger.error("无法连接到WebSocket服务")
        return {
            "success": False,
            "message": "登录服务不可用，请稍后重试"
        }
    except Exception as e:
        logger.error(f"账号密码登录异常: {e}")
        return {
            "success": False,
            "message": f"登录失败: {str(e)}"
        }


@router.get("/check/{session_id}")
async def check_login_status(
    session_id: str,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    检查账号密码登录状态
    
    代理请求到WebSocket服务查询状态
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.websocket_service_url}/password-login/check/{session_id}"
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"WebSocket服务返回错误: {response.status_code}")
                return {
                    "status": "error",
                    "message": f"查询服务异常: {response.status_code}"
                }
                
    except httpx.ConnectError:
        logger.error("无法连接到WebSocket服务")
        return {
            "status": "error",
            "message": "登录服务不可用，请稍后重试"
        }
    except Exception as e:
        logger.error(f"检查登录状态异常: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.delete("/cancel/{session_id}")
async def cancel_login(
    session_id: str,
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    取消登录会话
    
    代理请求到WebSocket服务取消登录
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{settings.websocket_service_url}/password-login/cancel/{session_id}"
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"WebSocket服务返回错误: {response.status_code}")
                return {
                    "success": False,
                    "message": f"取消服务异常: {response.status_code}"
                }
                
    except httpx.ConnectError:
        logger.error("无法连接到WebSocket服务")
        return {
            "success": False,
            "message": "登录服务不可用，请稍后重试"
        }
    except Exception as e:
        logger.error(f"取消登录会话异常: {e}")
        return {
            "success": False,
            "message": str(e)
        }
