"""定时任务执行范围的时间校验工具。"""
from __future__ import annotations

import re
from datetime import datetime


_DAILY_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def validate_daily_time_range(start_time: str, end_time: str) -> tuple[str, str]:
    """校验同一自然日内的 HH:MM 执行范围并返回规范化值。"""
    if not isinstance(start_time, str) or not isinstance(end_time, str):
        raise ValueError("执行时间必须使用 HH:MM 格式")

    start_value = start_time.strip()
    end_value = end_time.strip()
    if not _DAILY_TIME_PATTERN.fullmatch(start_value) or not _DAILY_TIME_PATTERN.fullmatch(end_value):
        raise ValueError("执行时间必须使用 HH:MM 格式")

    start_minutes = int(start_value[:2]) * 60 + int(start_value[3:])
    end_minutes = int(end_value[:2]) * 60 + int(end_value[3:])
    if start_minutes > end_minutes:
        raise ValueError("开始时间不能晚于结束时间")
    return start_value, end_value


def is_within_daily_time_range(now: datetime, start_time: str, end_time: str) -> bool:
    """判断给定时间是否落在同一自然日内、两端均包含的 HH:MM 范围。"""
    start_value, end_value = validate_daily_time_range(start_time, end_time)
    current_minutes = now.hour * 60 + now.minute
    start_minutes = int(start_value[:2]) * 60 + int(start_value[3:])
    end_minutes = int(end_value[:2]) * 60 + int(end_value[3:])
    return start_minutes <= current_minutes <= end_minutes
