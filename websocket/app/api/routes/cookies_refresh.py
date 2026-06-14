"""
COOKIES续期内部接口

功能：
1. 对外提供 WebSocket 服务内部 COOKIES 浏览器续期接口
2. 在 WebSocket 进程中执行浏览器续期
3. 返回浏览器提取到的完整 Cookie 快照
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select

from common.db.session import async_session_maker
from common.models.xy_account import XYAccount
from common.services.captcha.concurrency import run_browser_task
from common.services.cookie_renew_browser_service import cookie_renew_browser_service
from app.services.xianyu.cookies_refresh_service import cookies_refresh_service

router = APIRouter(prefix="/internal", tags=["internal"])


class CookiesRefreshRequest(BaseModel):
    """COOKIES续期请求。"""

    account_id: str


class BrowserRenewRequest(BaseModel):
    """浏览器续期委托请求（由 scheduler / backend-web 调用）。"""

    account_id: str
    cookies_str: str


@router.post("/cookies/browser-renew")
async def browser_renew(request: BrowserRenewRequest) -> dict[str, Any]:
    """在 WebSocket 进程内执行浏览器续期（复用持久化目录与账号级互斥锁）。

    供 scheduler / backend-web 通过 HTTP 委托调用，保证所有浏览器续期都收敛到
    WebSocket 进程，与滑块验证同进程串行执行，避免跨进程并发占用同一持久化目录。
    """
    logger.info(f"【内部API】收到账号 {request.account_id} 的浏览器续期委托请求")
    try:
        # renew_local 为同步阻塞执行（内部含等待槽位/账号锁 + 浏览器操作），
        # 走浏览器任务专用线程池，避免占用 asyncio 默认线程池拖垮 aiohttp 网络请求
        result = await run_browser_task(
            cookie_renew_browser_service.renew_local,
            request.cookies_str,
            request.account_id,
        )
        return {
            "success": result.success,
            "code": 200,
            "message": result.message,
            "data": {
                "has_quick_enter": result.has_quick_enter,
                "new_cookies_str": result.new_cookies_str,
                "updated_cookie_names": result.updated_cookie_names,
            },
        }
    except Exception as exc:
        logger.error(f"【内部API】账号 {request.account_id} 浏览器续期委托异常: {exc}")
        return {
            "success": False,
            "code": 500,
            "message": f"浏览器续期失败: {exc}",
            "data": {
                "has_quick_enter": False,
                "new_cookies_str": "",
                "updated_cookie_names": [],
            },
        }


@router.post("/cookies/refresh")
async def refresh_cookies(request: CookiesRefreshRequest) -> dict[str, Any]:
    """执行账号 COOKIES 浏览器续期。"""
    logger.info(f"【内部API】收到账号 {request.account_id} 的 COOKIES续期请求")
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(XYAccount).where(XYAccount.account_id == request.account_id)
            )
            account = result.scalar_one_or_none()

        if not account:
            return {
                "success": False,
                "code": 404,
                "message": f"账号不存在: {request.account_id}",
                "data": None,
            }

        browser_result = await cookies_refresh_service.refresh_account_cookies(
            account_id=account.account_id,
            cookie=account.cookie or "",
            metadata_json=account.metadata_json,
        )

        if not browser_result.success:
            logger.warning(f"【内部API】账号 {account.account_id} COOKIES续期接口执行失败: {browser_result.message}")
            return {
                "success": False,
                "code": 200,
                "message": browser_result.message,
                "data": {
                    "account_id": account.account_id,
                    "cookies": browser_result.cookies,
                },
            }

        return {
            "success": True,
            "code": 200,
            "message": browser_result.message,
            "data": {
                "account_id": account.account_id,
                "cookies": browser_result.cookies,
            },
        }
    except Exception as exc:
        logger.error(f"【内部API】账号 {request.account_id} COOKIES续期异常: {exc}")
        return {
            "success": False,
            "code": 500,
            "message": f"COOKIES续期失败: {exc}",
            "data": None,
        }
