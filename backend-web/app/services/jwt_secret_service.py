"""
JWT 密钥自检与持久化服务（纯数据库托管）

设计：JWT 密钥完全由数据库 xy_system_settings 表（key=security.jwt_secret_key）托管，
不再依赖 .env / 环境变量：
- 启动时若数据库已存在有效密钥 → 直接采用（保证重启一致，不重复踢用户下线）；
- 数据库无密钥或为弱值 → 生成强随机密钥并写入数据库，再采用；
- 采用的密钥写回进程内 settings.jwt_secret_key，使后续签发/校验立即生效。

为什么放数据库而非 .env：
- 单一权威数据源，部署脚本与环境变量都无需再管理密钥，避免多处来源不一致；
- 源码裸启动 / Docker 部署走的是同一套逻辑，行为统一；
- 重启后从库读取同一密钥，不会每次重启都让用户掉线。

说明：仅 backend-web 校验用户 JWT（websocket/scheduler 不依赖该密钥，经全量检索确认），
因此只需在 backend-web 启动时处理，不存在跨服务密钥同步问题。
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.system_setting import SystemSetting
from common.utils.security import generate_jwt_secret, is_weak_jwt_secret

# 数据库中存储 JWT 密钥的设置项 key
_JWT_SECRET_SETTING_KEY = "security.jwt_secret_key"
_JWT_SECRET_SETTING_DESC = "系统 JWT 密钥（由数据库统一托管，自动生成，请勿泄露）"


async def _load_persisted_secret(session: AsyncSession) -> str | None:
    """从数据库读取已持久化的密钥；不存在或为弱值时返回 None。"""
    result = await session.execute(
        select(SystemSetting.value).where(SystemSetting.key == _JWT_SECRET_SETTING_KEY)
    )
    row = result.scalar_one_or_none()
    if row and not is_weak_jwt_secret(row):
        return row
    return None


async def _persist_secret(session: AsyncSession, secret: str) -> None:
    """将密钥写入数据库（存在则更新，不存在则插入）。"""
    result = await session.execute(
        select(SystemSetting).where(SystemSetting.key == _JWT_SECRET_SETTING_KEY)
    )
    record = result.scalar_one_or_none()
    if record:
        record.value = secret
    else:
        record = SystemSetting(
            key=_JWT_SECRET_SETTING_KEY,
            value=secret,
            description=_JWT_SECRET_SETTING_DESC,
        )
    session.add(record)
    await session.commit()


async def ensure_jwt_secret_key(settings) -> None:
    """确保运行期存在一个稳定可用的强 JWT 密钥（纯数据库托管）。

    逻辑（不读取环境变量 / .env 中的 JWT_SECRET_KEY）：
    1. 数据库已有有效密钥 → 采用。
    2. 数据库无密钥（或为弱值）→ 生成强随机密钥并写入数据库，再采用。
    3. 将采用的密钥写回进程内 settings.jwt_secret_key，使后续签发/校验立即生效。

    Args:
        settings: 当前服务的配置实例（需可写 jwt_secret_key 属性）。
    """
    try:
        async with async_session_maker() as session:
            persisted = await _load_persisted_secret(session)
            if persisted:
                settings.jwt_secret_key = persisted
                logger.info("JWT 密钥已从数据库加载（统一托管，重启保持一致）")
                return

            # 数据库中没有可用密钥：生成并持久化
            new_secret = generate_jwt_secret()
            await _persist_secret(session, new_secret)
            settings.jwt_secret_key = new_secret
            logger.warning(
                "数据库中未找到 JWT 密钥，已自动生成强随机密钥并持久化；"
                "如有已登录用户，需重新登录一次（仅此一次）"
            )
    except Exception as e:
        # 数据库不可用等异常不应阻断启动；此时退回使用配置默认值，仅告警
        logger.opt(exception=e).error(
            "初始化 JWT 密钥失败（数据库不可用？），本次启动将使用配置默认值；恢复数据库后重启即可统一托管"
        )
