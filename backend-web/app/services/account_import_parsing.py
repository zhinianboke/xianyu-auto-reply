"""Excel 导入解析公共方法：读取 Sheet 并规范化布尔、整数、文本及 JSON 值。"""
from __future__ import annotations

import json
from typing import Any

def _parse_bool(value: str | None) -> bool:
    """解析布尔值：'是'/True/'true'/'1' → True，其余 → False"""
    if value is None:
        return False
    v = str(value).strip().lower()
    return v in ("是", "true", "1", "yes")


def _parse_int(value: str | None, default: int = 0) -> int:
    """解析整数，失败返回默认值"""
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default


def _parse_str(value: Any) -> str:
    """解析字符串，None → 空字符串"""
    if value is None:
        return ""
    return str(value).strip()


def _parse_json(value: str | None) -> Any:
    """解析JSON字符串，失败返回None"""
    if not value or str(value).strip() == "":
        return None
    try:
        return json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return None


def _read_sheet_rows(wb, sheet_name: str) -> list[dict[str, str]]:
    """读取Sheet为字典列表（表头作为key）"""
    if sheet_name not in wb.sheetnames:
        return []
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return []
    headers = [str(h or "").strip() for h in rows[0]]
    result = []
    for row in rows[1:]:
        row_dict = {}
        for i, header in enumerate(headers):
            if not header:
                continue
            val = row[i] if i < len(row) else None
            row_dict[header] = str(val).strip() if val is not None else ""
        # 跳过全空行
        if any(v for v in row_dict.values()):
            result.append(row_dict)
    return result
