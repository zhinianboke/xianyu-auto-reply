"""
公开账号查询接口。

功能：
1. 无需登录，使用个人设置中的分销秘钥校验身份。
2. 返回秘钥所属用户账号管理中全部已启用账号的账号 ID 和备注。
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.routes.external_api_route import ExternalApiRoute
from app.services.external_account_service import ExternalAccountService
from common.schemas.common import ApiResponse


router = APIRouter(
    prefix="/external/enabled-accounts",
    tags=["公开账号查询"],
    route_class=ExternalApiRoute,
)


class EnabledAccountsResponse(ApiResponse):
    """公开账号查询统一响应。"""

    code: int


class EnabledAccountsRequest(BaseModel):
    """公开查询已启用账号的请求参数。"""

    secret_key: str | None = None


@router.post("", response_model=EnabledAccountsResponse)
async def list_enabled_accounts(
    payload: EnabledAccountsRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> EnabledAccountsResponse:
    """
    根据分销秘钥获取所属用户全部已启用账号。

    Args:
        payload: 包含必填分销秘钥的请求体。
        session: 数据库会话。
    Returns:
        统一响应；成功数据包含 accounts 和 total。
    """
    secret_key = (payload.secret_key if payload else "") or ""
    secret_key = secret_key.strip()
    if not secret_key:
        return EnabledAccountsResponse(success=False, code=40001, message="秘钥不能为空", data=None)
    if len(secret_key) > 128:
        return EnabledAccountsResponse(
            success=False,
            code=40001,
            message="秘钥长度不能超过128位",
            data=None,
        )

    accounts = await ExternalAccountService(session).list_enabled_accounts_by_secret(secret_key)
    if accounts is None:
        return EnabledAccountsResponse(success=False, code=40001, message="秘钥不存在", data=None)
    return EnabledAccountsResponse(
        success=True,
        code=200,
        message="查询成功",
        data={"accounts": accounts, "total": len(accounts)},
    )


__all__ = ["router"]
