"""用户角色字典初始化：随统一数据库启动自检仅补齐缺失角色，保留已有配置。"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from common.models.user import UserRole

USER_ROLE_DICTIONARY = "user_role"
USER_ROLE_DICTIONARY_ITEMS = (
    (UserRole.ADMIN.value, "管理员", 10),
    (UserRole.OPERATOR.value, "运营人员", 20),
    (UserRole.MEMBER.value, "普通用户", 30),
)


async def ensure_user_role_dictionary(conn: AsyncConnection) -> None:
    """幂等补齐用户角色中文字典，异常交给启动入口明确报告。

    Args:
        conn: 统一数据库初始化入口提供的连接，字典表已完成自检。
    Returns:
        无返回值；已有值、中文名称和启用状态均保持原样。
    """
    for value, label, sort_order in USER_ROLE_DICTIONARY_ITEMS:
        await conn.execute(text(
            "INSERT IGNORE INTO xy_data_dictionaries "
            "(dict_type, dict_value, dict_label, sort_order, enabled) "
            "VALUES (:dict_type, :dict_value, :dict_label, :sort_order, 1)"
        ), {
            "dict_type": USER_ROLE_DICTIONARY,
            "dict_value": value,
            "dict_label": label,
            "sort_order": sort_order,
        })
    logger.info("用户角色字典自检完成，共 {} 项", len(USER_ROLE_DICTIONARY_ITEMS))
