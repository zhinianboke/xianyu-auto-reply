"""
商品监控分类访问校验

功能：
1. 统一校验"某分类是否存在、且当前用户有权引用"
2. 供监控任务（listing_monitor_service）与兜底账号配置（collect/order_fallback_account_service）复用，
   避免归属校验在多处各写一遍导致标准漂移

权限口径：
- 普通用户：只能引用自己创建的分类，防止构造请求挂用他人分类（会泄露他人分类名称，
  并让对方无法删除自己的分类）；
- 管理员：可引用任意用户的分类——"管理员·本分类"兜底层就是按用户的分类ID配置的，
  这是兜底覆盖链（本用户·本分类 → 本用户·无分类 → 管理员·本分类 → 管理员·无分类）的前提。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from common.models.listing_monitor_category import ListingMonitorCategory


async def ensure_category_accessible(
    session: AsyncSession,
    category_id: Optional[int],
    owner_id: Optional[int],
    is_admin: bool = False,
) -> Optional[ListingMonitorCategory]:
    """校验分类存在且当前用户有权引用，返回分类对象。

    Args:
        session: 数据库会话
        category_id: 分类ID；None 表示"无分类"，直接放行并返回 None
        owner_id: 引用方用户ID（普通用户即本人ID）
        is_admin: 是否管理员；管理员不受归属限制

    Returns:
        校验通过的分类对象；category_id 为 None 时返回 None

    Raises:
        ValueError: 分类不存在/已删除，或无权限引用他人分类
    """
    if category_id is None:
        return None

    category = await session.get(ListingMonitorCategory, category_id)
    if not category or category.is_deleted:
        raise ValueError("所选分类不存在")
    # 普通用户只能引用自己创建的分类；管理员不受限
    if not is_admin and owner_id is not None and category.owner_id != owner_id:
        raise ValueError("所选分类不存在或无权限使用")
    return category


__all__ = ["ensure_category_accessible"]
