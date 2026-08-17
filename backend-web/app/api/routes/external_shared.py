"""
公开接口公共校验与响应。

功能：
1. 提供全部公开接口共用的统一响应模型（HTTP 恒为 200，业务状态放在 success 和 code）。
2. 统一校验分销秘钥、闲鱼账号 ID 这两个公开接口共有的身份字段。
3. 统一按分销秘钥定位账号，并把账号访问异常转换为业务响应。
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.external_account_service import (
    ExternalAccountAccessError,
    ExternalAccountService,
)
from common.models.xy_account import XYAccount
from common.schemas.common import ApiResponse

# 与 users.secret_key、xy_accounts.account_id 字段长度保持一致
MAX_SECRET_KEY_LENGTH = 128
MAX_ACCOUNT_ID_LENGTH = 80


class ExternalApiResponse(ApiResponse):
    """公开接口统一响应，各公开接口共用同一个模型。"""

    code: int


def normalize_text(value: str | None) -> str:
    """规范化可空文本字段，去除首尾空格。"""
    return (value or "").strip()


def external_error(code: int, message: str) -> ExternalApiResponse:
    """
    构造公开接口业务错误响应。

    Args:
        code: 业务错误码。
        message: 展示给调用方的中文错误信息。
    Returns:
        success 为 False 的统一响应。
    """
    return ExternalApiResponse(success=False, code=code, message=message, data=None)


def validate_secret_key(secret_key: str | None) -> tuple[str, ExternalApiResponse | None]:
    """
    校验分销秘钥字段。

    Args:
        secret_key: 个人设置-分销管理中的分销秘钥。
    Returns:
        规范化后的秘钥和错误响应，校验通过时错误响应为 None。
    """
    normalized_secret = normalize_text(secret_key)
    if not normalized_secret:
        return "", external_error(40001, "秘钥不能为空")
    if len(normalized_secret) > MAX_SECRET_KEY_LENGTH:
        return "", external_error(40001, f"秘钥长度不能超过{MAX_SECRET_KEY_LENGTH}位")
    return normalized_secret, None


def validate_identity_fields(
    secret_key: str | None,
    account_id: str | None,
) -> tuple[str, str, ExternalApiResponse | None]:
    """
    校验公开接口共有的秘钥和闲鱼账号 ID。

    Args:
        secret_key: 个人设置-分销管理中的分销秘钥。
        account_id: 公开账号列表接口返回的闲鱼账号 ID。
    Returns:
        规范化后的秘钥、账号 ID 和错误响应，校验通过时错误响应为 None。
    """
    normalized_secret, error = validate_secret_key(secret_key)
    if error:
        return "", "", error
    normalized_account_id = normalize_text(account_id)
    if not normalized_account_id:
        return "", "", external_error(40002, "闲鱼账号ID不能为空")
    if len(normalized_account_id) > MAX_ACCOUNT_ID_LENGTH:
        return "", "", external_error(40002, f"闲鱼账号ID长度不能超过{MAX_ACCOUNT_ID_LENGTH}位")
    return normalized_secret, normalized_account_id, None


async def resolve_external_account(
    session: AsyncSession,
    secret_key: str,
    account_id: str,
    scene: str,
) -> tuple[XYAccount | None, ExternalApiResponse | None]:
    """
    按分销秘钥定位调用方指定的闲鱼账号，只校验归属不校验启用状态。

    Args:
        session: 数据库会话。
        secret_key: 已规范化的分销秘钥。
        account_id: 已规范化的闲鱼账号 ID。
        scene: 日志场景名称，如“公开发布”“公开分类接口”。
    Returns:
        账号记录和错误响应，二者其一为 None。
    """
    try:
        account = await ExternalAccountService(session).get_account_by_secret(
            secret_key,
            account_id,
        )
        return account, None
    except ExternalAccountAccessError as exc:
        return None, external_error(exc.code, exc.message)
    except Exception as exc:
        logger.error(f"{scene}账号校验异常: account_id={account_id}, error={exc}")
        return None, external_error(50001, "账号信息查询失败，请稍后重试")


__all__ = [
    "MAX_ACCOUNT_ID_LENGTH",
    "MAX_SECRET_KEY_LENGTH",
    "ExternalApiResponse",
    "external_error",
    "normalize_text",
    "resolve_external_account",
    "validate_identity_fields",
    "validate_secret_key",
]
