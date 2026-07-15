"""
北京时间工具模块

功能：
1. 统一提供北京时间时区常量
2. 统一提供带时区和不带时区的北京时间获取方法
3. 统一提供 datetime 安全序列化为 ISO 字符串的方法
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from common.core.config import get_settings

BEIJING_TZ = timezone(timedelta(hours=8))

# IM Token 缓存 TTL 的兜底默认区间（小时），当环境变量未配置或配置非法时使用
DEFAULT_TOKEN_CACHE_TTL_MIN_HOURS = 5.0
DEFAULT_TOKEN_CACHE_TTL_MAX_HOURS = 10.0

# 在基础过期时间上追加的秒级随机偏移，进一步分散批量账号的 Token 到期时间
TOKEN_CACHE_EXPIRY_JITTER_MIN_SECONDS = 60 * 60
TOKEN_CACHE_EXPIRY_JITTER_MAX_SECONDS = 5 * 60 * 60


def get_beijing_now() -> datetime:
    """获取当前北京时间。"""
    return datetime.now(BEIJING_TZ)



def get_beijing_now_naive() -> datetime:
    """获取当前北京时间（去掉时区信息，便于写入DATETIME字段）。"""
    return get_beijing_now().replace(tzinfo=None)


def safe_isoformat(value: Optional[datetime]) -> Optional[str]:
    """安全地将 ``datetime`` 序列化为 ISO 8601 字符串。

    替代项目中大量重复的 ``value.isoformat() if value else None`` 模板，
    保持与该模板**完全等价**的行为：仅在 ``value`` 为真值时调用 ``isoformat()``，
    否则返回 ``None``。本函数不做时区转换，调用方传入什么时区就输出什么时区，
    避免对前端契约引入隐式行为变化。

    Args:
        value: 待序列化的 ``datetime`` 对象，允许 ``None``。

    Returns:
        ``value.isoformat()`` 字符串；当 ``value`` 为 ``None`` 或其他假值时返回 ``None``。
    """
    return value.isoformat() if value else None


def random_token_cache_expiry() -> Tuple[datetime, float]:
    """生成 IM Token 缓存（``xy_token_cache`` 表）的随机过期时间。

    先在环境变量配置的基础区间内随机取 TTL 小时数：
    ``TOKEN_CACHE_TTL_MIN_HOURS`` ~ ``TOKEN_CACHE_TTL_MAX_HOURS``，
    未配置时默认 5~10 小时；配置非法（任一值 <=0 或 min>max）时回退默认区间。
    得到基础过期时间后，再追加 1~5 小时的秒级随机偏移。默认配置下，最终
    TTL 为 6~15 小时；两段随机共同避免大量账号 Token 同一时刻集中过期。

    Returns:
        ``(expire_at, ttl_hours)``：精确到秒的北京时间过期时刻（naive datetime）
        与包含额外随机偏移的最终 TTL 小时数。
    """
    settings = get_settings()
    low = settings.token_cache_ttl_min_hours
    high = settings.token_cache_ttl_max_hours
    # 配置非法时回退默认，避免出现负数或区间反转
    if low <= 0 or high <= 0 or low > high:
        low = DEFAULT_TOKEN_CACHE_TTL_MIN_HOURS
        high = DEFAULT_TOKEN_CACHE_TTL_MAX_HOURS
    base_ttl_hours = random.uniform(low, high)
    base_expire_at = get_beijing_now_naive() + timedelta(hours=base_ttl_hours)

    # 使用整秒随机值，确保额外偏移可细分到秒，同时兼容 MySQL DATETIME 秒精度。
    jitter_seconds = random.randint(
        TOKEN_CACHE_EXPIRY_JITTER_MIN_SECONDS,
        TOKEN_CACHE_EXPIRY_JITTER_MAX_SECONDS,
    )
    expire_at = (base_expire_at + timedelta(seconds=jitter_seconds)).replace(microsecond=0)
    total_ttl_hours = base_ttl_hours + jitter_seconds / 3600
    return expire_at, total_ttl_hours
