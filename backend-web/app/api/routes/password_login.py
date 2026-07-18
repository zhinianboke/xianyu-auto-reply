"""
密码登录路由 - Backend-Web服务

功能：
1. 账号密码登录入口：按模式分流——协议方式（本进程执行）/ 浏览器方式（代理 websocket）
2. 登录状态查询：pl_ 前缀→本地协议会话（校验归属）；否则→代理 websocket
3. 取消登录：同上双路

模式选择（password_login.mode）：
- browser：强制浏览器（代理 websocket，现状不变）
- protocol：强制协议（不做运行期回退）
- 历史 auto、缺失值或非法值：按 browser 处理，不再读取环境变量决定登录方式
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import get_settings
from app.services.account_service import AccountService
from app.services.password_login import password_login_manager
from app.services.password_login.manager import SESSION_PREFIX
from common.models.system_setting import SystemSetting
from common.models.user import User
from common.services.account_limit_service import AccountLimitExceededError, AccountLimitService

router = APIRouter(prefix="/password-login", tags=["密码登录"])

settings = get_settings()


# ==================== 请求模型 ====================

class PasswordLoginRequest(BaseModel):
    """密码登录请求"""
    account_id: str
    account: str
    password: str
    show_browser: bool = False


# ==================== 模式判定 ====================

async def _decide_mode(db: AsyncSession) -> bool:
    """严格按系统设置决定走协议还是浏览器。

    Returns:
        是否使用协议登录
    """
    rows = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.key == "password_login.mode"
        )
    )).scalars().all()
    m = {r.key: (r.value or "").strip() for r in rows}

    mode = (m.get("password_login.mode") or "browser").lower()
    if mode == "protocol":
        return True
    if mode != "browser":
        logger.warning(f"账号密码登录方式 {mode or '空'} 无效，按浏览器登录处理")
    return False


# ==================== 路由 ====================

@router.post("")
async def password_login(
    request: PasswordLoginRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
):
    """账号密码登录入口：按模式分流协议/浏览器。"""
    if not request.account_id or not request.account or not request.password:
        return {"success": False, "message": "账号ID、登录账号和密码不能为空"}

    # 新账号先做限额校验（快速失败）
    existing = await account_service.get_account_for_user(current_user.id, request.account_id)
    if not existing:
        try:
            await AccountLimitService(account_service.session).ensure_can_add_account(current_user.id)
        except AccountLimitExceededError as exc:
            return {"success": False, "message": str(exc)}

    use_protocol = await _decide_mode(account_service.session)
    logger.info(
        f"【{current_user.username}】账号密码登录 {request.account_id}: "
        f"{'协议' if use_protocol else '浏览器'}模式"
    )

    if use_protocol:
        session_id = password_login_manager.start(
            account_id=request.account_id,
            account=request.account,
            password=request.password,
            show_browser=request.show_browser,
            owner_id=current_user.id,
        )
        return {
            "success": True,
            "session_id": session_id,
            "status": "processing",
            "message": "登录任务已启动，请等待...",
        }

    # 浏览器方式：代理到 websocket（现状不变）
    return await _proxy_ws_login(request, current_user.id)


async def _proxy_ws_login(request: PasswordLoginRequest, user_id: int) -> dict:
    """代理浏览器登录到 websocket 服务。"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.websocket_service_url}/password-login",
                json={
                    "account_id": request.account_id,
                    "account": request.account,
                    "password": request.password,
                    "show_browser": True,  # 浏览器方式强制有头
                    "user_id": user_id,
                },
            )
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"WebSocket服务返回错误: {resp.status_code}")
            return {"success": False, "message": f"登录服务异常: {resp.status_code}"}
    except httpx.ConnectError:
        logger.error("无法连接到WebSocket服务")
        return {"success": False, "message": "登录服务不可用，请稍后重试"}
    except Exception as e:
        logger.error(f"账号密码登录异常: {e}")
        return {"success": False, "message": f"登录失败: {str(e)}"}


@router.get("/check/{session_id}")
async def check_login_status(
    session_id: str,
    current_user: User = Depends(deps.get_current_active_user),
):
    """查询登录状态：pl_ 前缀→本地协议会话（校验归属）；否则→代理 websocket。"""
    # 本地协议会话
    if session_id.startswith(SESSION_PREFIX):
        result = password_login_manager.get_status(session_id, current_user.id)
        if result is None:
            return {"status": "not_found", "message": "会话不存在或已过期"}
        return result

    # 浏览器会话：代理 websocket
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.websocket_service_url}/password-login/check/{session_id}"
            )
            if resp.status_code == 200:
                return resp.json()
            return {"status": "error", "message": f"查询服务异常: {resp.status_code}"}
    except httpx.ConnectError:
        return {"status": "error", "message": "登录服务不可用，请稍后重试"}
    except Exception as e:
        logger.error(f"检查登录状态异常: {e}")
        return {"status": "error", "message": str(e)}


@router.delete("/cancel/{session_id}")
async def cancel_login(
    session_id: str,
    current_user: User = Depends(deps.get_current_active_user),
):
    """取消登录会话：pl_ 前缀→本地协议会话（校验归属）；否则→代理 websocket。"""
    if session_id.startswith(SESSION_PREFIX):
        ok = password_login_manager.cancel(session_id, current_user.id)
        return {"success": ok, "message": "登录会话已取消" if ok else "会话不存在"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{settings.websocket_service_url}/password-login/cancel/{session_id}"
            )
            if resp.status_code == 200:
                return resp.json()
            return {"success": False, "message": f"取消服务异常: {resp.status_code}"}
    except httpx.ConnectError:
        return {"success": False, "message": "登录服务不可用，请稍后重试"}
    except Exception as e:
        logger.error(f"取消登录会话异常: {e}")
        return {"success": False, "message": str(e)}
