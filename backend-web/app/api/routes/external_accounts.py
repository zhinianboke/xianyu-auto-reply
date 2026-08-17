"""
公开账号查询接口。

功能：
1. 无需登录，使用个人设置中的分销秘钥校验身份。
2. 返回秘钥所属用户账号管理中全部账号的账号 ID、备注和启用状态。
3. 禁用账号同样返回，通过 enabled 字段标识，且不影响其调用公开分类和发布接口。
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.routes.external_api_route import ExternalApiRoute
from app.api.routes.external_shared import (
    ExternalApiResponse,
    external_error,
    validate_secret_key,
)
from app.services.external_account_service import ExternalAccountService


router = APIRouter(
    prefix="/external/enabled-accounts",
    tags=["公开账号查询"],
    route_class=ExternalApiRoute,
)


class EnabledAccountsRequest(BaseModel):
    """公开查询账号列表的请求参数。"""

    secret_key: str | None = None


@router.post("", response_model=ExternalApiResponse)
async def list_enabled_accounts(
    payload: EnabledAccountsRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ExternalApiResponse:
    """
    根据分销秘钥获取所属用户全部账号（含禁用账号）。

    Args:
        payload: 包含必填分销秘钥的请求体。
        session: 数据库会话。
    Returns:
        统一响应；成功数据包含 accounts、total、enabled_total 和 disabled_total。
        accounts 每项的 enabled 为 False 时表示该账号在账号管理中已禁用，仅作状态提示。
    """
    secret_key, error = validate_secret_key(payload.secret_key if payload else None)
    if error:
        return error

    # 数据库异常也要落到公开接口统一的业务错误码，与账号校验、分类、发布接口保持一致
    try:
        accounts = await ExternalAccountService(session).list_accounts_by_secret(secret_key)
    except Exception as exc:
        logger.error(f"公开账号列表查询异常: error={exc}")
        return external_error(50001, "账号信息查询失败，请稍后重试")
    if accounts is None:
        return external_error(40001, "秘钥不存在")
    enabled_total = sum(1 for account in accounts if account.get("enabled"))
    return ExternalApiResponse(
        success=True,
        code=200,
        message="查询成功",
        data={
            "accounts": accounts,
            "total": len(accounts),
            "enabled_total": enabled_total,
            "disabled_total": len(accounts) - enabled_total,
        },
    )


__all__ = ["router"]
