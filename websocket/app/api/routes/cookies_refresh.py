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
from app.services.xianyu.cookies_refresh_service import cookies_refresh_service

router = APIRouter(prefix="/internal", tags=["internal"])


class CookiesRefreshRequest(BaseModel):
    """COOKIES续期请求。"""

    account_id: str


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
