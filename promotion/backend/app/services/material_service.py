"""
返佣系统 - 素材库服务

功能：
1. 素材分页查询（支持关键词搜索）
2. 素材更新（修改标题、售价、描述、图片、推广链接、淘口令）
3. 素材删除
4. 批量写入素材（供定时任务调用）
"""
from __future__ import annotations

import json

from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.fy_material import (
    FYMaterial,
    PUBLISH_STATUS_FAILED,
    PUBLISH_STATUS_PUBLISHED,
    PUBLISH_STATUS_UNPUBLISHED,
    VALID_PUBLISH_STATUS_VALUES,
    normalize_publish_status,
)


async def list_materials(
    session: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    account_id: str = "",
    is_admin: bool = False,
    publish_status: str = "",
    legacy_published: str = "",
) -> dict:
    """
    分页查询素材

    Args:
        session: 数据库会话
        user_id: 用户ID
        page: 页码
        page_size: 每页条数
        keyword: 搜索关键词（匹配标题或描述）
        account_id: 闲鱼账号ID筛选
        is_admin: 是否管理员（管理员查看所有用户数据）
        publish_status: 发布状态筛选（unpublished/published/failed）
        legacy_published: 兼容旧版发布状态筛选（"1"=已发布，"0"=未发布）

    Returns:
        包含素材列表和总数的字典
    """
    # 基础条件：管理员不过滤owner_id
    conditions = [] if is_admin else [FYMaterial.owner_id == user_id]
    if keyword.strip():
        kw = f"%{keyword.strip()}%"
        conditions.append(
            or_(FYMaterial.title.ilike(kw), FYMaterial.description.ilike(kw), FYMaterial.coupon_info.ilike(kw))
        )
    if account_id.strip():
        conditions.append(FYMaterial.account_id == account_id.strip())
    filter_status = _normalize_publish_status_filter(publish_status=publish_status, legacy_published=legacy_published)
    if filter_status:
        conditions.append(FYMaterial.publish_status == filter_status)

    # 总数
    count_stmt = select(func.count()).select_from(FYMaterial).where(*conditions)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # 分页列表
    offset = (page - 1) * page_size
    list_stmt = (
        select(FYMaterial)
        .where(*conditions)
        .order_by(FYMaterial.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(list_stmt)
    materials = result.scalars().all()

    return {
        "success": True,
        "data": {
            "list": [_material_to_dict(m) for m in materials],
            "total": total,
        },
    }


async def update_material(
    session: AsyncSession,
    user_id: int,
    material_id: int,
    data: dict,
) -> dict:
    """
    更新素材信息

    Args:
        session: 数据库会话
        user_id: 用户ID
        material_id: 素材ID
        data: 更新数据

    Returns:
        更新结果
    """
    material = await _get_user_material(session, user_id, material_id)
    if not material:
        return {"success": False, "message": "素材不存在或无权限"}

    if "title" in data:
        material.title = (data["title"] or "").strip()
    if "price" in data:
        material.price = float(data["price"] or 0.1)
    if "description" in data:
        material.description = (data["description"] or "").strip() or None
    if "images" in data:
        material.images = data["images"] if isinstance(data["images"], str) else json.dumps(data["images"])
    if "click_url" in data:
        material.click_url = (data["click_url"] or "").strip() or None
    if "coupon_url" in data:
        material.coupon_url = (data["coupon_url"] or "").strip() or None
    if "coupon_info" in data:
        material.coupon_info = (data["coupon_info"] or "").strip() or None
    if "tpwd" in data:
        material.tpwd = (data["tpwd"] or "").strip() or None
    if "short_url" in data:
        material.short_url = (data["short_url"] or "").strip() or None

    await session.commit()
    await session.refresh(material)
    logger.info(f"用户{user_id}更新素材: id={material.id}")
    return {"success": True, "data": _material_to_dict(material)}


async def delete_material(
    session: AsyncSession,
    user_id: int,
    material_id: int,
) -> dict:
    """
    删除素材

    Args:
        session: 数据库会话
        user_id: 用户ID
        material_id: 素材ID

    Returns:
        删除结果
    """
    material = await _get_user_material(session, user_id, material_id)
    if not material:
        return {"success": False, "message": "素材不存在或无权限"}

    await session.delete(material)
    await session.commit()
    logger.info(f"用户{user_id}删除素材: id={material_id}")
    return {"success": True, "message": "删除成功"}


async def batch_delete_materials(
    session: AsyncSession,
    user_id: int,
    ids: list[int],
) -> dict:
    """
    批量删除素材

    Args:
        session: 数据库会话
        user_id: 用户ID
        ids: 素材ID列表

    Returns:
        删除结果
    """
    if not ids:
        return {"success": False, "message": "请选择要删除的素材"}

    stmt = select(FYMaterial).where(
        FYMaterial.id.in_(ids),
        FYMaterial.owner_id == user_id,
    )
    result = await session.execute(stmt)
    materials = result.scalars().all()

    if not materials:
        return {"success": False, "message": "未找到可删除的素材"}

    for m in materials:
        await session.delete(m)
    await session.commit()
    logger.info(f"用户{user_id}批量删除素材: {len(materials)}条")
    return {"success": True, "message": f"成功删除{len(materials)}条素材"}


def _normalize_material_items(items: list[dict]) -> list[dict]:
    unique_items: list[dict] = []
    seen_item_ids: set[str] = set()
    seen_titles: set[str] = set()
    for it in items:
        item_id = str(it.get("item_id") or "").strip()
        title = str(it.get("title") or "").strip()
        if not item_id:
            continue
        if item_id in seen_item_ids:
            continue
        if title and title in seen_titles:
            continue
        unique_items.append({**it, "item_id": item_id, "title": title})
        seen_item_ids.add(item_id)
        if title:
            seen_titles.add(title)
    return unique_items


async def _get_material_upsert_context(
    session: AsyncSession,
    user_id: int,
    account_id: str,
    items: list[dict],
) -> tuple[list[dict], dict[str, FYMaterial], set[str]]:
    normalized_account_id = str(account_id or "").strip()
    unique_items = _normalize_material_items(items)
    if not unique_items:
        return [], {}, set()

    item_ids = [it["item_id"] for it in unique_items]
    titles = [it["title"] for it in unique_items if it["title"]]
    existing_conditions = [
        FYMaterial.owner_id == user_id,
        FYMaterial.account_id == normalized_account_id,
    ]
    if titles:
        existing_conditions.append(or_(FYMaterial.item_id.in_(item_ids), FYMaterial.title.in_(titles)))
    else:
        existing_conditions.append(FYMaterial.item_id.in_(item_ids))

    existing_stmt = select(FYMaterial).where(*existing_conditions)
    existing_result = await session.execute(existing_stmt)
    existing_rows = existing_result.scalars().all()
    existing_materials = {
        str(material.item_id or "").strip(): material
        for material in existing_rows
        if str(material.item_id or "").strip()
    }
    existing_titles = {
        str(material.title or "").strip()
        for material in existing_rows
        if str(material.title or "").strip()
    }
    return unique_items, existing_materials, existing_titles


def _can_create_material(
    item_id: str,
    title: str,
    existing_materials: dict[str, FYMaterial],
    existing_titles: set[str],
) -> bool:
    if item_id in existing_materials:
        return False
    if title and title in existing_titles:
        return False
    return True


async def collect_creatable_material_items(
    session: AsyncSession,
    user_id: int,
    account_id: str,
    items: list[dict],
) -> list[dict]:
    unique_items, existing_materials, existing_titles = await _get_material_upsert_context(
        session=session,
        user_id=user_id,
        account_id=account_id,
        items=items,
    )
    if not unique_items:
        return []

    creatable_items: list[dict] = []
    reserved_titles = set(existing_titles)
    for it in unique_items:
        item_id = it["item_id"]
        title = it["title"]
        if not _can_create_material(item_id, title, existing_materials, reserved_titles):
            continue
        creatable_items.append(it)
        if title:
            reserved_titles.add(title)
    return creatable_items


async def batch_create_materials(
    session: AsyncSession,
    user_id: int,
    account_id: str,
    rule_id: int,
    items: list[dict],
) -> int:
    """
    批量写入素材（供定时任务调用）

    自动去重：同一用户同一闲鱼账号下同一商品ID不会重复插入

    Args:
        session: 数据库会话
        user_id: 用户ID
        account_id: 闲鱼账号ID
        rule_id: 来源选品规则ID
        items: 商品列表

    Returns:
        实际新增数量
    """
    if not items:
        return 0

    normalized_account_id = str(account_id or "").strip()
    unique_items, existing_materials, existing_titles = await _get_material_upsert_context(
        session=session,
        user_id=user_id,
        account_id=normalized_account_id,
        items=items,
    )
    if not unique_items:
        return 0

    count = 0
    updated_count = 0
    for it in unique_items:
        item_id = it["item_id"]
        title = it["title"]
        existing_material = existing_materials.get(item_id)
        if existing_material:
            changed = False
            click_url = (it.get("click_url") or "").strip() or None
            coupon_url = (it.get("coupon_url") or "").strip() or None
            coupon_info = (it.get("coupon_info") or "").strip() or None
            description = (it.get("description") or "").strip() or None
            tpwd = (it.get("tpwd") or "").strip() or None
            short_url = (it.get("short_url") or "").strip() or None
            if click_url and existing_material.click_url != click_url:
                existing_material.click_url = click_url
                changed = True
            if coupon_url and existing_material.coupon_url != coupon_url:
                existing_material.coupon_url = coupon_url
                changed = True
            if coupon_info and existing_material.coupon_info != coupon_info:
                existing_material.coupon_info = coupon_info
                changed = True
            if description and existing_material.description != description:
                existing_material.description = description
                changed = True
            if tpwd and existing_material.tpwd != tpwd:
                existing_material.tpwd = tpwd
                changed = True
            if short_url and existing_material.short_url != short_url:
                existing_material.short_url = short_url
                changed = True
            if changed:
                updated_count += 1
            continue
        if not _can_create_material(item_id, title, existing_materials, existing_titles):
            continue
        stock = int(it.get("stock", 999) or 999)
        material = FYMaterial(
            owner_id=user_id,
            account_id=normalized_account_id,
            rule_id=rule_id,
            item_id=item_id,
            title=it.get("title", ""),
            price=float(it.get("price", 0.1) or 0.1),
            stock=stock,
            description=it.get("description", ""),
            images=json.dumps(it.get("images", [])) if isinstance(it.get("images"), list) else (it.get("images") or "[]"),
            click_url=it.get("click_url", ""),
            coupon_url=it.get("coupon_url", ""),
            coupon_info=it.get("coupon_info", ""),
            tpwd=it.get("tpwd", ""),
            short_url=it.get("short_url", ""),
            original_price=it.get("original_price", ""),
            promotion_price=it.get("promotion_price", ""),
            commission_rate=it.get("commission_rate", ""),
            commission_amount=it.get("commission_amount", ""),
            shop_title=it.get("shop_title", ""),
            volume=it.get("volume", ""),
            publish_status=PUBLISH_STATUS_UNPUBLISHED,
        )
        session.add(material)
        if title:
            existing_titles.add(title)
        count += 1

    if count > 0 or updated_count > 0:
        await session.commit()
    logger.info(f"用户{user_id}账号{normalized_account_id}规则{rule_id}批量写入素材: 新增{count}条，更新重复{updated_count}条，跳过重复{len(items) - count - updated_count}条")
    return count


async def _get_user_material(session: AsyncSession, user_id: int, material_id: int):
    """获取用户的指定素材"""
    stmt = select(FYMaterial).where(
        FYMaterial.id == material_id,
        FYMaterial.owner_id == user_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _normalize_publish_status_filter(publish_status: str, legacy_published: str) -> str:
    normalized_status = str(publish_status or "").strip().lower()
    if normalized_status in VALID_PUBLISH_STATUS_VALUES:
        return normalized_status
    legacy_value = str(legacy_published or "").strip()
    if legacy_value == "1":
        return PUBLISH_STATUS_PUBLISHED
    if legacy_value == "0":
        return PUBLISH_STATUS_UNPUBLISHED
    return ""


def _material_to_dict(m) -> dict:
    """将素材ORM对象转为字典"""
    # 解析images字段
    images = []
    if m.images:
        try:
            images = json.loads(m.images) if isinstance(m.images, str) else m.images
        except (json.JSONDecodeError, TypeError):
            images = []
    publish_status = normalize_publish_status(getattr(m, "publish_status", None), getattr(m, "published", None))

    return {
        "id": m.id,
        "owner_id": m.owner_id,
        "account_id": m.account_id or "",
        "rule_id": m.rule_id or 0,
        "item_id": m.item_id,
        "title": m.title or "",
        "price": float(m.price) if m.price else 0.1,
        "stock": int(m.stock) if m.stock is not None else 999,
        "description": m.description or "",
        "images": images,
        "click_url": m.click_url or "",
        "coupon_url": m.coupon_url or "",
        "coupon_info": m.coupon_info or "",
        "tpwd": m.tpwd or "",
        "short_url": m.short_url or "",
        "original_price": m.original_price or "",
        "promotion_price": m.promotion_price or "",
        "commission_rate": m.commission_rate or "",
        "commission_amount": m.commission_amount or "",
        "shop_title": m.shop_title or "",
        "volume": m.volume or "",
        "publish_status": publish_status,
        "published": publish_status == PUBLISH_STATUS_PUBLISHED,
        "published_at": m.published_at.strftime("%Y-%m-%d %H:%M:%S") if m.published_at else "",
        "published_item_id": m.published_item_id or "",
        "publish_random_str": m.publish_random_str or "",
        "created_at": m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else "",
        "updated_at": m.updated_at.strftime("%Y-%m-%d %H:%M:%S") if m.updated_at else "",
    }
