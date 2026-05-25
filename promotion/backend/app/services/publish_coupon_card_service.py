"""
推广返佣系统 - 发布后自动建卡服务

功能：
1. 在商品发布成功后自动创建文本卡券
2. 将卡券关联到发布后的商品ID
3. 对重复创建和数据库短暂异常进行兜底处理
"""
from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.card import Card
from common.models.card_item_relation import CardItemRelation
from common.models.fy_material import FYMaterial
from common.services.backend_web_loader import load_backend_web_class

AUTO_PUBLISH_CARD_TYPE = "text"
AUTO_PUBLISH_CARD_NAME_SUFFIX = "[自动优惠链接]"
AUTO_PUBLISH_CARD_DESCRIPTION = "复制以下内容打开淘宝即可######{DELIVERY_CONTENT}"
AUTO_PUBLISH_CARD_LEGACY_DESCRIPTION = "发布商品成功后自动创建的优惠链接卡券"
AUTO_PUBLISH_CARD_LEGACY_CONTENT_PREFIX = "您购买的商品优惠链接为："

_publish_coupon_card_locks: dict[str, asyncio.Lock] = {}
_publish_coupon_card_locks_guard = asyncio.Lock()


def _get_card_service_class():
    """动态加载 backend-web 中的卡券服务类。"""
    return load_backend_web_class(
        module_name="common.services._backend_web_card_service",
        relative_path="backend-web/app/services/card_service.py",
        class_name="CardService",
    )


def _build_auto_card_name(material_title: str) -> str:
    """根据素材标题生成自动卡券名称。"""
    base_title = (material_title or "").strip() or "商品"
    max_title_length = max(1, 255 - len(AUTO_PUBLISH_CARD_NAME_SUFFIX))
    return f"{base_title[:max_title_length]}{AUTO_PUBLISH_CARD_NAME_SUFFIX}"


def _build_auto_card_content(tpwd: str) -> str:
    """构建自动卡券的文本内容。"""
    return (tpwd or "").strip()


async def _get_publish_coupon_card_lock(user_id: int, published_item_id: str) -> asyncio.Lock:
    lock_key = f"{user_id}:{published_item_id}"
    async with _publish_coupon_card_locks_guard:
        lock = _publish_coupon_card_locks.get(lock_key)
        if lock is None:
            lock = asyncio.Lock()
            _publish_coupon_card_locks[lock_key] = lock
        return lock


async def ensure_publish_coupon_card(
    material_id: int,
    user_id: int,
    published_item_id: str,
) -> dict:
    """确保发布成功后的商品已自动创建优惠链接文本卡券。"""
    normalized_item_id = str(published_item_id or "").strip()
    if not normalized_item_id:
        return {"success": False, "message": "发布后商品ID为空，跳过自动建卡"}

    lock = await _get_publish_coupon_card_lock(user_id=user_id, published_item_id=normalized_item_id)
    async with lock:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with async_session_maker() as session:
                    return await _ensure_publish_coupon_card_once(
                        session=session,
                        material_id=material_id,
                        user_id=user_id,
                        published_item_id=normalized_item_id,
                    )
            except Exception as exc:
                last_error = exc
                logger.warning(f"素材[{material_id}]自动建卡失败，第{attempt + 1}次重试: {exc}")
                await asyncio.sleep(1)
        if last_error:
            raise last_error
        return {"success": False, "message": "自动建卡失败"}


async def _ensure_publish_coupon_card_once(
    session: AsyncSession,
    material_id: int,
    user_id: int,
    published_item_id: str,
) -> dict:
    """使用单次数据库会话处理自动建卡逻辑。"""
    material_stmt = select(FYMaterial).where(
        FYMaterial.id == material_id,
        FYMaterial.owner_id == user_id,
    )
    material_result = await session.execute(material_stmt)
    material = material_result.scalar_one_or_none()
    if not material:
        return {"success": False, "message": f"素材[{material_id}]不存在，跳过自动建卡"}

    tpwd = (material.tpwd or "").strip()
    if not tpwd:
        logger.warning(f"素材[{material.id}]没有淘口令，跳过自动建卡")
        return {"success": False, "message": "素材没有淘口令，跳过自动建卡"}

    card_name = _build_auto_card_name(material.title or "")
    card_content = _build_auto_card_content(tpwd)
    existing_card = await _find_existing_auto_card(
        session=session,
        user_id=user_id,
        published_item_id=published_item_id,
        card_name=card_name,
    )
    if existing_card:
        changed = _apply_auto_card_fields(existing_card, published_item_id, card_content)
        card_service_class = _get_card_service_class()
        bind_result = await _bind_card_to_item(
            card_service=card_service_class(session),
            user_id=user_id,
            card_id=existing_card.id,
            published_item_id=published_item_id,
        )
        if changed:
            await session.commit()
            logger.info(f"素材[{material.id}]自动卡券已更新: card_id={existing_card.id}, item_id={published_item_id}")
            return {"success": True, "created": False, "updated": True, "card_id": existing_card.id, **bind_result}
        logger.info(f"素材[{material.id}]自动卡券已存在，无需重复创建: card_id={existing_card.id}, item_id={published_item_id}")
        return {"success": True, "created": False, "updated": False, "card_id": existing_card.id, **bind_result}

    card_service_class = _get_card_service_class()
    card_service = card_service_class(session)
    try:
        card_id = await card_service.create_card(
            user_id=user_id,
            item_id=published_item_id,
            name=card_name,
            card_type=AUTO_PUBLISH_CARD_TYPE,
            text_content=card_content,
            description=AUTO_PUBLISH_CARD_DESCRIPTION,
            enabled=True,
            delay_seconds=0,
            is_dockable=False,
            is_multi_spec=False,
        )
        bind_result = await _bind_card_to_item(
            card_service=card_service,
            user_id=user_id,
            card_id=card_id,
            published_item_id=published_item_id,
        )
        logger.info(f"素材[{material.id}]发布成功后自动创建卡券成功: card_id={card_id}, item_id={published_item_id}")
        return {"success": True, "created": True, "updated": False, "card_id": card_id, **bind_result}
    except ValueError:
        existing_card = await _find_existing_auto_card(
            session=session,
            user_id=user_id,
            published_item_id=published_item_id,
            card_name=card_name,
        )
        if not existing_card:
            raise
        changed = _apply_auto_card_fields(existing_card, published_item_id, card_content)
        bind_result = await _bind_card_to_item(
            card_service=card_service,
            user_id=user_id,
            card_id=existing_card.id,
            published_item_id=published_item_id,
        )
        if changed:
            await session.commit()
        logger.info(f"素材[{material.id}]自动卡券命中重复校验，已复用现有卡券: card_id={existing_card.id}, item_id={published_item_id}")
        return {"success": True, "created": False, "updated": changed, "card_id": existing_card.id, **bind_result}


async def get_publish_coupon_card_status(
    material_id: int,
    user_id: int,
    published_item_id: str,
) -> dict:
    normalized_item_id = str(published_item_id or "").strip()
    if not normalized_item_id:
        return {"success": False, "ready": False, "message": "发布后商品ID为空"}

    async with async_session_maker() as session:
        material_stmt = select(FYMaterial).where(
            FYMaterial.id == material_id,
            FYMaterial.owner_id == user_id,
        )
        material_result = await session.execute(material_stmt)
        material = material_result.scalar_one_or_none()
        if not material:
            return {"success": False, "ready": False, "message": f"素材[{material_id}]不存在"}

        tpwd = (material.tpwd or "").strip()
        if not tpwd:
            return {"success": False, "ready": False, "message": "素材没有淘口令"}

        card_name = _build_auto_card_name(material.title or "")
        card_content = _build_auto_card_content(tpwd)
        existing_card = await _find_existing_auto_card(
            session=session,
            user_id=user_id,
            published_item_id=normalized_item_id,
            card_name=card_name,
        )
        if not existing_card:
            return {"success": True, "ready": False, "card_exists": False, "relation_exists": False, "card_id": None}

        relation_exists = await _has_card_item_relation(
            session=session,
            card_id=existing_card.id,
            published_item_id=normalized_item_id,
        )
        return {
            "success": True,
            "ready": _is_auto_card_ready(existing_card, normalized_item_id, card_content, relation_exists),
            "card_exists": True,
            "relation_exists": relation_exists,
            "card_id": existing_card.id,
        }


async def _find_existing_auto_card(
    session: AsyncSession,
    user_id: int,
    published_item_id: str,
    card_name: str,
):
    """查询当前商品是否已存在自动创建的优惠链接卡券。"""
    stmt = (
        select(Card)
        .outerjoin(
            CardItemRelation,
            and_(
                CardItemRelation.card_id == Card.id,
                CardItemRelation.item_id == published_item_id,
            ),
        )
        .where(
            Card.user_id == user_id,
            or_(
                Card.item_id == published_item_id,
                CardItemRelation.id.is_not(None),
            ),
            Card.name == card_name,
            Card.type == AUTO_PUBLISH_CARD_TYPE,
            Card.is_multi_spec == False,
            or_(
                Card.description == AUTO_PUBLISH_CARD_DESCRIPTION,
                Card.description == AUTO_PUBLISH_CARD_LEGACY_DESCRIPTION,
                Card.text_content.like(f"{AUTO_PUBLISH_CARD_LEGACY_CONTENT_PREFIX}%"),
            ),
        )
        .order_by(Card.id.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def _has_card_item_relation(session: AsyncSession, card_id: int, published_item_id: str) -> bool:
    stmt = select(CardItemRelation.id).where(
        CardItemRelation.card_id == card_id,
        CardItemRelation.item_id == published_item_id,
    ).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _bind_card_to_item(card_service, user_id: int, card_id: int, published_item_id: str) -> dict:
    """将自动卡券绑定到商品关联表，重复绑定时保持幂等。"""
    bind_result = await card_service.batch_bind_cards_to_items(
        user_id=user_id,
        card_ids=[card_id],
        item_ids=[published_item_id],
    )
    return {
        "bind_success_count": bind_result.get("success_count", 0),
        "bind_fail_count": bind_result.get("fail_count", 0),
    }


def _is_auto_card_ready(card: Card, published_item_id: str, card_content: str, relation_exists: bool) -> bool:
    return (
        card.item_id == published_item_id
        and card.type == AUTO_PUBLISH_CARD_TYPE
        and card.text_content == card_content
        and card.description == AUTO_PUBLISH_CARD_DESCRIPTION
        and card.enabled is True
        and card.delay_seconds == 0
        and card.api_config is None
        and card.data_content is None
        and card.image_url is None
        and card.image_urls is None
        and relation_exists
    )


def _apply_auto_card_fields(card: Card, published_item_id: str, card_content: str) -> bool:
    """将自动卡券的标准字段写回已有卡券。"""
    changed = False
    if card.item_id != published_item_id:
        card.item_id = published_item_id
        changed = True
    if card.type != AUTO_PUBLISH_CARD_TYPE:
        card.type = AUTO_PUBLISH_CARD_TYPE
        changed = True
    if card.text_content != card_content:
        card.text_content = card_content
        changed = True
    if card.description != AUTO_PUBLISH_CARD_DESCRIPTION:
        card.description = AUTO_PUBLISH_CARD_DESCRIPTION
        changed = True
    if card.enabled is not True:
        card.enabled = True
        changed = True
    if card.delay_seconds != 0:
        card.delay_seconds = 0
        changed = True
    if card.api_config is not None:
        card.api_config = None
        changed = True
    if card.data_content is not None:
        card.data_content = None
        changed = True
    if card.image_url is not None:
        card.image_url = None
        changed = True
    if card.image_urls is not None:
        card.image_urls = None
        changed = True
    return changed
