"""服务间 API 令牌初始化与持久化。"""
from __future__ import annotations

import secrets

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from common.core.config import get_settings as get_common_settings
from common.db.session import async_session_maker
from common.models.system_setting import SystemSetting
from common.utils.internal_auth import MIN_INTERNAL_TOKEN_LENGTH

INTERNAL_TOKEN_SETTING_KEY = "security.internal_api_token"
INTERNAL_TOKEN_SETTING_DESC = "服务间内部 API 共享令牌（自动生成并持久化，请勿泄露）"


def _generate_internal_token() -> str:
    """生成强随机服务间令牌。"""
    return secrets.token_urlsafe(48)


async def ensure_internal_api_token(settings) -> str:
    """加载或生成服务间令牌，并写回当前服务及公共配置。"""
    configured = (getattr(settings, "internal_api_token", "") or "").strip()
    if configured and len(configured) < MIN_INTERNAL_TOKEN_LENGTH:
        raise ValueError("INTERNAL_API_TOKEN 长度不足32位")

    async with async_session_maker() as session:
        result = await session.execute(
            select(SystemSetting)
            .where(SystemSetting.key == INTERNAL_TOKEN_SETTING_KEY)
            .with_for_update()
        )
        record = result.scalar_one_or_none()

        if record and len((record.value or "").strip()) >= MIN_INTERNAL_TOKEN_LENGTH:
            token = record.value.strip()
        else:
            token = configured or _generate_internal_token()
            if record:
                record.value = token
                record.description = INTERNAL_TOKEN_SETTING_DESC
                await session.commit()
            else:
                session.add(SystemSetting(
                    key=INTERNAL_TOKEN_SETTING_KEY,
                    value=token,
                    description=INTERNAL_TOKEN_SETTING_DESC,
                ))
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    result = await session.execute(
                        select(SystemSetting.value).where(
                            SystemSetting.key == INTERNAL_TOKEN_SETTING_KEY
                        )
                    )
                    persisted = result.scalar_one_or_none()
                    if not persisted or len(persisted.strip()) < MIN_INTERNAL_TOKEN_LENGTH:
                        raise
                    token = persisted.strip()

    settings.internal_api_token = token
    # common 服务模块使用独立的 BaseConfig 实例，也同步写回，避免公共调用链拿到空令牌。
    get_common_settings().internal_api_token = token
    logger.info("内部 API 令牌已从数据库加载或自动初始化")
    return token


async def load_internal_api_token(settings) -> str:
    """
    只读取已有的服务间 API 令牌，不创建或修改数据库记录。

    Args:
        settings: 当前服务配置对象。
    Returns:
        已加载的服务间 API 令牌。
    Raises:
        ValueError: 环境变量中的令牌长度不足。
        RuntimeError: 数据库和环境变量中都没有有效令牌。
    """
    configured = (getattr(settings, "internal_api_token", "") or "").strip()
    if configured and len(configured) < MIN_INTERNAL_TOKEN_LENGTH:
        raise ValueError("INTERNAL_API_TOKEN 长度不足32位")

    async with async_session_maker() as session:
        result = await session.execute(
            select(SystemSetting.value).where(
                SystemSetting.key == INTERNAL_TOKEN_SETTING_KEY
            )
        )
        persisted = result.scalar_one_or_none()

    token = (persisted or configured or "").strip()
    if len(token) < MIN_INTERNAL_TOKEN_LENGTH:
        raise RuntimeError(
            "服务间 API 令牌未初始化，请先启动 backend 完成数据库初始化"
        )

    settings.internal_api_token = token
    get_common_settings().internal_api_token = token
    logger.info("内部 API 令牌已从现有配置加载，当前服务未写入数据库")
    return token
