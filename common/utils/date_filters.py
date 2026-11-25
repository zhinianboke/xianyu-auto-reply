"""北京时间日期查询边界：统一解析日期，以原时间列的左闭右开区间查询整天数据。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def parse_filter_date(value: str | None, label: str) -> datetime | None:
    """解析可选YYYY-MM-DD为北京时间零点；空值返回None，非法格式抛出中文ValueError。"""
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{label}格式不正确，请使用年-月-日格式") from exc
    if parsed.date().isoformat() != value:
        raise ValueError(f"{label}格式不正确，请使用年-月-日格式")
    return parsed


def next_day_start(value: datetime) -> datetime:
    """返回指定北京时间日期的次日零点作为开区间上界；超出datetime范围时明确报错。"""
    try:
        return value.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    except OverflowError as exc:
        raise ValueError("结束日期过大，无法计算次日零点，请选择9999-12-30或更早的日期") from exc


def date_filter_bounds(start_date: str | None, end_date: str | None) -> tuple[datetime | None, datetime | None]:
    """校验开始/结束日期并返回北京时间下界和次日零点上界；未提交的边界为None。"""
    start = parse_filter_date(start_date, "开始日期")
    end = parse_filter_date(end_date, "结束日期")
    if start is not None and end is not None and start > end:
        raise ValueError("开始日期不能晚于结束日期")
    return start, next_day_start(end) if end is not None else None


def date_range_conditions(column: Any, start_date: str | None, end_date: str | None) -> list:
    """返回原时间列的整天筛选表达式列表；参数为ORM时间列及日期，总数和列表可共同复用。"""
    start, end = date_filter_bounds(start_date, end_date)
    conditions = []
    if start is not None:
        conditions.append(column >= start)
    if end is not None:
        conditions.append(column < end)
    return conditions
