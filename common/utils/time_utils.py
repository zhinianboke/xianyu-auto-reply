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

    TTL 小时数在环境变量配置的区间内随机取值：
    ``TOKEN_CACHE_TTL_MIN_HOURS`` ~ ``TOKEN_CACHE_TTL_MAX_HOURS``，
    未配置时默认 5~10 小时；配置非法（任一值 <=0 或 min>max）时回退默认区间。
    区间随机可避免大量账号 Token 同一时刻集中过期、触发并发刷新。

    Returns:
        ``(expire_at, ttl_hours)``：北京时间的过期时刻（naive datetime）
        与本次随机出的 TTL 小时数。
    """
    settings = get_settings()
    low = settings.token_cache_ttl_min_hours
    high = settings.token_cache_ttl_max_hours
    # 配置非法时回退默认，避免出现负数或区间反转
    if low <= 0 or high <= 0 or low > high:
        low = DEFAULT_TOKEN_CACHE_TTL_MIN_HOURS
        high = DEFAULT_TOKEN_CACHE_TTL_MAX_HOURS
    ttl_hours = random.uniform(low, high)
    expire_at = get_beijing_now_naive() + timedelta(hours=ttl_hours)
    return expire_at, ttl_hours
