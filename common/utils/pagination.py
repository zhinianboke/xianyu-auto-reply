"""
分页查询通用工具

功能:
1. ``execute_paginated_with_filters`` - 一次性构建 list_stmt 与 count_stmt，
   消除业务代码中 "双重 where 过滤" 的重复（即过滤条件需要分别写到 select 与 count
   两条语句上的常见反模式）。同时支持页码模式 (page/page_size) 与偏移模式
   (limit/offset)，以兼容不同 Service 的现有签名。
2. ``build_pagination_response`` - 构建项目中常用的标准分页响应字典
   ``{list, total, page, page_size, total_pages}``。

使用约定:
- 该模块只处理 SQLAlchemy 异步会话上的简单分页查询；如果业务包含 ``union_all``
  或多分支条件（例如 ``auto_reply_log_service``），不要强行使用此工具。
- 调用方负责传入自己已经构造好的 ORM 模型与过滤表达式，工具内部不知道业务语义。
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def execute_paginated_with_filters(
    session: AsyncSession,
    model: Any,
    *,
    filters: Optional[Iterable[Any]] = None,
    order_by: Optional[Iterable[Any]] = None,
    page: Optional[int] = None,
    page_size: int = 20,
    limit: Optional[int] = None,
    offset: int = 0,
) -> tuple[list[Any], int]:
    """执行分页查询，返回 ``(records, total)``。

    内部一次性构建 ``list_stmt`` 与 ``count_stmt``，自动把 ``filters`` 应用到两边，
    避免业务代码在两条 SQL 上重复写过滤条件。

    分页参数二选一：
    - **页码模式**：传入 ``page`` 与 ``page_size``。
    - **偏移模式**：传入 ``limit`` 与 ``offset``，用于现有 ``limit/offset`` 风格签名。

    Args:
        session: SQLAlchemy 异步会话。
        model: 要查询的 ORM 模型类。
        filters: SQLAlchemy 布尔表达式列表；为空时不加任何 ``where`` 条件。
        order_by: SQLAlchemy 排序表达式列表；为空时按数据库默认顺序返回。
        page: 页码（从 1 开始）；当传入时启用页码模式。
        page_size: 每页数量；页码模式必填，偏移模式作为兜底。
        limit: 每页/单次查询数量；当 ``page`` 为 ``None`` 时启用偏移模式。
        offset: 偏移量；偏移模式下使用，页码模式忽略。

    Returns:
        ``(records, total)``：当前分页的 ORM 对象列表 + 满足条件的总记录数。
    """
    filter_list = list(filters or [])
    order_list = list(order_by or [])

    list_stmt = select(model)
    count_stmt = select(func.count()).select_from(model)

    if filter_list:
        list_stmt = list_stmt.where(*filter_list)
        count_stmt = count_stmt.where(*filter_list)

    if order_list:
        list_stmt = list_stmt.order_by(*order_list)

    if page is not None:
        # 页码模式：page 至少为 1，避免负偏移
        actual_offset = max(int(page) - 1, 0) * int(page_size)
        actual_limit = int(page_size)
    else:
        actual_offset = int(offset)
        actual_limit = int(limit) if limit is not None else int(page_size)

    list_stmt = list_stmt.offset(actual_offset).limit(actual_limit)

    total = (await session.execute(count_stmt)).scalar() or 0
    result = await session.execute(list_stmt)
    return list(result.scalars().all()), int(total)


def build_pagination_response(
    items: list[Any],
    total: int,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """构建项目内常用的标准分页响应字典。

    Args:
        items: 当前页的数据项列表（通常已序列化为 dict）。
        total: 总记录数。
        page: 当前页码。
        page_size: 每页数量。

    Returns:
        ``{"list": items, "total": total, "page": page, "page_size": page_size,
        "total_pages": total_pages}``，其中 ``total_pages`` 在 ``total`` 为 0
        时返回 0，避免出现 ``0/page_size`` 仍为 1 的边界情况。
    """
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return {
        "list": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


__all__ = [
    "execute_paginated_with_filters",
    "build_pagination_response",
]
