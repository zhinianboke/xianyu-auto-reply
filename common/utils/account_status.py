"""闲鱼账号状态判断公共工具。"""
from __future__ import annotations


INACTIVE_ACCOUNT_STATUSES = frozenset({"inactive", "disabled", "suspended", "deleted"})


def is_account_active(status: str | None) -> bool:
    """判断账号是否可用于后台自动任务。"""
    normalized = (status or "").strip().lower()
    return normalized not in INACTIVE_ACCOUNT_STATUSES
