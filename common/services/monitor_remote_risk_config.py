"""
商品监控 - 远程过风控配置（按用户隔离）

功能：
1. 统一管理「远程过风控」配置在用户个人设置表（xy_user_settings）中的存储键
2. 提供按用户读取 / 保存配置的方法，供 backend-web 接口与 scheduler 定时任务共用
3. 提供远程服务URL的合法性校验，保存与调用前统一口径

说明：
- 配置保存在个人设置中，每个用户单独一份，互不影响（管理员也只维护自己的一份）。
- 采集触发风控（FAIL_SYS_USER_VALIDATE / RGV587 / punish 等）时，若该用户配置了
  远程服务URL与秘钥，则调用远程服务求解验证链接，拿到 x5sec 后用同账号重试采集。
"""
from __future__ import annotations

from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.user_setting import UserSetting

# 个人设置存储键：远程过风控服务地址 / 调用秘钥
MONITOR_REMOTE_RISK_URL_KEY = "monitor.remote_risk_url"
MONITOR_REMOTE_RISK_SECRET_KEY = "monitor.remote_risk_secret"

# 存储键对应的中文描述（写入个人设置表的 description 字段）
_KEY_DESCRIPTIONS = {
    MONITOR_REMOTE_RISK_URL_KEY: "商品监控-远程过风控服务URL",
    MONITOR_REMOTE_RISK_SECRET_KEY: "商品监控-远程过风控秘钥",
}

# URL 最大长度（与个人设置 value 为 Text 无关，仅做输入约束，避免误粘贴超长内容）
MAX_URL_LENGTH = 500
# 秘钥最大长度
MAX_SECRET_LENGTH = 200


def validate_remote_risk_url(url: str) -> Optional[str]:
    """
    校验远程过风控服务URL是否合法。

    Args:
        url: 用户填写的远程服务URL（允许为空，表示不启用）
    Returns:
        校验不通过时返回中文错误信息；通过返回 None
    """
    normalized = (url or "").strip()
    if not normalized:
        return None
    if not normalized.lower().startswith(("http://", "https://")):
        return "远程服务URL 必须以 http:// 或 https:// 开头"
    if len(normalized) > MAX_URL_LENGTH:
        return f"远程服务URL 长度不能超过 {MAX_URL_LENGTH} 个字符"
    return None


def validate_remote_risk_secret(secret: str) -> Optional[str]:
    """
    校验远程过风控秘钥是否合法。

    Args:
        secret: 用户填写的秘钥（允许为空，表示不启用）
    Returns:
        校验不通过时返回中文错误信息；通过返回 None
    """
    if len((secret or "").strip()) > MAX_SECRET_LENGTH:
        return f"秘钥长度不能超过 {MAX_SECRET_LENGTH} 个字符"
    return None


async def get_remote_risk_config(session: AsyncSession, user_id: Optional[int]) -> Dict[str, str]:
    """
    读取指定用户的远程过风控配置。

    Args:
        session: 数据库会话
        user_id: 用户ID（为空时返回空配置）
    Returns:
        {"url": 远程服务URL, "secret": 秘钥}，未配置的项为空字符串
    """
    empty = {"url": "", "secret": ""}
    if not user_id:
        return empty

    stmt = select(UserSetting.key, UserSetting.value).where(
        UserSetting.user_id == user_id,
        UserSetting.key.in_([MONITOR_REMOTE_RISK_URL_KEY, MONITOR_REMOTE_RISK_SECRET_KEY]),
    ).order_by(UserSetting.id)
    result = await session.execute(stmt)
    # 个人设置表未建 (user_id, key) 唯一约束，历史并发可能留下同键多行，按 id 升序取最后一条（最新）
    values = {row[0]: (row[1] or "").strip() for row in result.all()}
    return {
        "url": values.get(MONITOR_REMOTE_RISK_URL_KEY, ""),
        "secret": values.get(MONITOR_REMOTE_RISK_SECRET_KEY, ""),
    }


def is_remote_risk_enabled(config: Optional[Dict[str, str]]) -> bool:
    """远程过风控是否可用：URL 与秘钥都填写了才视为启用。"""
    if not config:
        return False
    return bool((config.get("url") or "").strip() and (config.get("secret") or "").strip())


async def save_remote_risk_config(
    session: AsyncSession,
    user_id: int,
    url: str,
    secret: str,
) -> Dict[str, str]:
    """
    保存指定用户的远程过风控配置（存在则更新，不存在则新增）。

    Args:
        session: 数据库会话
        user_id: 用户ID
        url: 远程服务URL（空串表示不启用）
        secret: 调用秘钥（空串表示不启用）
    Returns:
        保存后的配置 {"url": ..., "secret": ...}
    """
    payload = {
        MONITOR_REMOTE_RISK_URL_KEY: (url or "").strip(),
        MONITOR_REMOTE_RISK_SECRET_KEY: (secret or "").strip(),
    }

    stmt = select(UserSetting).where(
        UserSetting.user_id == user_id,
        UserSetting.key.in_(list(payload.keys())),
    ).order_by(UserSetting.id)
    result = await session.execute(stmt)
    # 同键多行时以最新一行为准（后写覆盖），旧行保留不动，避免删除历史数据
    existing = {setting.key: setting for setting in result.scalars().all()}

    for key, value in payload.items():
        setting = existing.get(key)
        if setting:
            setting.value = value
            setting.description = _KEY_DESCRIPTIONS[key]
        else:
            session.add(UserSetting(
                user_id=user_id,
                key=key,
                value=value,
                description=_KEY_DESCRIPTIONS[key],
            ))

    await session.commit()
    return {
        "url": payload[MONITOR_REMOTE_RISK_URL_KEY],
        "secret": payload[MONITOR_REMOTE_RISK_SECRET_KEY],
    }


__all__ = [
    "MONITOR_REMOTE_RISK_URL_KEY",
    "MONITOR_REMOTE_RISK_SECRET_KEY",
    "MAX_URL_LENGTH",
    "MAX_SECRET_LENGTH",
    "validate_remote_risk_url",
    "validate_remote_risk_secret",
    "get_remote_risk_config",
    "is_remote_risk_enabled",
    "save_remote_risk_config",
]
