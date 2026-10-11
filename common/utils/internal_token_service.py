"""服务间 API 令牌初始化与持久化。"""
from __future__ import annotations

import secrets

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import SQLAlchemyError

from common.core.config import get_settings as get_common_settings
from common.db.session import async_session_maker
from common.models.system_setting import SystemSetting
from common.utils.internal_auth import MIN_INTERNAL_TOKEN_LENGTH

INTERNAL_TOKEN_SETTING_KEY = "security.internal_api_token"
INTERNAL_TOKEN_SETTING_DESC = "服务间内部 API 共享令牌（自动生成并持久化，请勿泄露）"


def _generate_internal_token() -> str:
    """生成强随机服务间令牌。"""
    return secrets.token_urlsafe(48)


def _normalize_token(value: str | None) -> str:
    """去除令牌首尾空白。"""
    return (value or "").strip()


def _is_usable_token(value: str | None) -> bool:
    """判断令牌长度是否满足内部鉴权要求。"""
    return len(_normalize_token(value)) >= MIN_INTERNAL_TOKEN_LENGTH


def _read_configured_token(settings) -> str:
    """读取环境变量中的令牌，长度不足时直接报错而不是继续用弱令牌。"""
    configured = _normalize_token(getattr(settings, "internal_api_token", ""))
    if configured and len(configured) < MIN_INTERNAL_TOKEN_LENGTH:
        raise ValueError("INTERNAL_API_TOKEN 长度不足32位")
    return configured


async def _fetch_persisted_token(session) -> str | None:
    """读取数据库中已持久化的令牌原始值。"""
    result = await session.execute(
        select(SystemSetting.value).where(SystemSetting.key == INTERNAL_TOKEN_SETTING_KEY)
    )
    return result.scalar_one_or_none()


async def _load_or_create_internal_token(configured: str) -> tuple[str, bool]:
    """
    读取数据库中已持久化的令牌；缺失或无效时生成/沿用配置值并落库后回读。

    并发保护（三个服务可能同时首次启动）：
    1. 记录不存在时用 ``INSERT ... ON DUPLICATE KEY UPDATE`` 幂等插入，重复键
       分支把主键赋回自身即不覆盖先写入的令牌，随后回读实际落库的值，因此并发
       插入只留一条记录且各服务拿到同一令牌。这里刻意不做 ``SELECT ... FOR
       UPDATE``：缺失行上的间隙锁会让并发插入的 insert intention 锁互相等待而死锁。
    2. 记录存在但值无效时用条件更新修复（仅当值仍是读到的旧值才生效），
       多个服务同时修复也只有一方写入，其余回读到同一令牌。

    Args:
        configured: 环境变量中配置的令牌，可为空字符串。
    Returns:
        (令牌, 本次调用是否实际写入了数据库)。
    Raises:
        RuntimeError: 写入后仍读不到有效令牌。
    """
    async with async_session_maker() as session:
        persisted = await _fetch_persisted_token(session)
        if _is_usable_token(persisted):
            return _normalize_token(persisted), False

        token = configured or _generate_internal_token()
        if persisted is None:
            statement = mysql_insert(SystemSetting).values(
                key=INTERNAL_TOKEN_SETTING_KEY,
                value=token,
                description=INTERNAL_TOKEN_SETTING_DESC,
            )
            # 重复键时把主键赋回自身：等价空操作，不会覆盖已存在的令牌。
            statement = statement.on_duplicate_key_update(key=SystemSetting.key)
            result = await session.execute(statement)
        else:
            result = await session.execute(
                update(SystemSetting)
                .where(
                    SystemSetting.key == INTERNAL_TOKEN_SETTING_KEY,
                    SystemSetting.value == persisted,
                )
                .values(value=token, description=INTERNAL_TOKEN_SETTING_DESC)
            )
        wrote = bool(result.rowcount)
        await session.commit()

        # 并发写入时落库的可能是其他服务的令牌，以回读结果为准。
        persisted = await _fetch_persisted_token(session)

    token = _normalize_token(persisted)
    if len(token) < MIN_INTERNAL_TOKEN_LENGTH:
        raise RuntimeError(
            "服务间 API 令牌未能写入数据库，请检查 xy_system_settings 表结构与写权限"
        )
    return token, wrote


async def ensure_internal_api_token(settings) -> str:
    """加载或生成服务间令牌，并写回当前服务及公共配置。"""
    configured = _read_configured_token(settings)
    token, _ = await _load_or_create_internal_token(configured)

    settings.internal_api_token = token
    # common 服务模块使用独立的 BaseConfig 实例，也同步写回，避免公共调用链拿到空令牌。
    get_common_settings().internal_api_token = token
    logger.info("内部 API 令牌已从数据库加载或自动初始化")
    return token


async def load_internal_api_token(settings) -> str:
    """
    加载服务间 API 令牌；数据库中缺失或无效时自动生成并持久化后返回。

    已存在的有效令牌不会被重新生成，因此 backend-web、scheduler、websocket
    无论启动顺序如何都会拿到同一令牌：令牌行丢失时由最先启动的服务补写，
    不再要求 backend-web 先启动。

    Args:
        settings: 当前服务配置对象。
    Returns:
        已加载的服务间 API 令牌。
    Raises:
        ValueError: 环境变量中的令牌长度不足。
        RuntimeError: 数据库中的令牌既读不到也写不进。
    """
    configured = _read_configured_token(settings)

    try:
        token, wrote = await _load_or_create_internal_token(configured)
    except SQLAlchemyError as exc:
        if not configured:
            raise
        # 数据库不可写（只读账号、表缺失等）时退回环境变量令牌：各服务的环境变量
        # 由同一份部署配置下发，令牌仍保持一致，不因此拒绝启动。
        logger.warning(f"服务间 API 令牌无法写入数据库，改用环境变量中的令牌: {exc}")
        token, wrote = configured, False

    settings.internal_api_token = token
    get_common_settings().internal_api_token = token
    if wrote:
        logger.warning("数据库中缺少服务间 API 令牌，本服务已自动生成并持久化，其余服务会加载到同一令牌")
    else:
        logger.info("内部 API 令牌已从数据库加载")
    return token
