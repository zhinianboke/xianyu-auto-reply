"""
Token 缓存有效期判断工具。

功能：
1. 统一判断原到期日是否有效
2. 原到期日失效时判断续期到期日是否有效
3. 为 WebSocket Token 刷新和续期任务提供一致的状态口径
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum


class TokenCacheValidity(str, Enum):
    """Token 缓存有效期状态。"""

    CURRENT = "current"
    RENEWED = "renewed"
    EXPIRED = "expired"


def classify_token_cache_validity(
    expire_at: datetime | None,
    renew_expire_at: datetime | None,
    now: datetime,
) -> TokenCacheValidity:
    """判断 Token 缓存当前应使用哪个有效期。

    Args:
        expire_at: 原到期日。
        renew_expire_at: 定时续期任务写入的续期到期日。
        now: 当前北京时间（无时区 datetime）。

    Returns:
        CURRENT 表示原到期日有效；RENEWED 表示仅续期到期日有效；
        EXPIRED 表示两个到期日都无效。
    """
    if expire_at is not None and expire_at > now:
        return TokenCacheValidity.CURRENT
    if renew_expire_at is not None and renew_expire_at > now:
        return TokenCacheValidity.RENEWED
    return TokenCacheValidity.EXPIRED
