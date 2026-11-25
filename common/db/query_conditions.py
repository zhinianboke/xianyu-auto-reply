"""数据库公共筛选条件：统一软删除的数值比较，保留模型及别名的数据隔离条件。"""
from __future__ import annotations

from typing import Any


def deletion_state(model: Any, is_deleted: bool):
    """返回软删除状态条件；参数为模型或别名及删除状态，适用于非空0/1字段。"""
    return model.is_deleted == int(is_deleted)


def not_deleted(model: Any):
    """返回未删除条件；参数为模型或别名，不包含权限筛选，也不将NULL当作未删除。"""
    return deletion_state(model, False)
