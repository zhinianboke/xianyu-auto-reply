"""
北京时间工具模块

功能：
1. 统一提供北京时间时区常量
2. 统一提供带时区和不带时区的北京时间获取方法
3. 统一提供 datetime 安全序列化为 ISO 字符串的方法
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

BEIJING_TZ = timezone(timedelta(hours=8))


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
