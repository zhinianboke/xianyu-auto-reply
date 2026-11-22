"""
返佣系统 - 商品删除后同步清理服务

功能：
1. 闲鱼平台商品删除成功后，同步清理主项目数据库中的关联数据
2. 删除 xy_catalog_items 中的商品记录
3. 软删除当前用户该商品的卡券关联，保留撤销历史
4. 软删除不再被其他商品或分销使用的旧绑定卡券，保留卡密
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.card import Card
from common.models.card_item_relation import CardItemRelation
from common.models.dock_record import DockRecord
from common.models.xy_catalog_item import XYCatalogItem
from common.services.card_access import dock_access_condition
from common.services.card_matcher import CardMatcher


async def sync_delete_item_from_db(
    session: AsyncSession,
    owner_id: int,
    item_id: str,
) -> None:
    """
    闲鱼商品删除成功后，同步清理主项目数据库中的关联数据

    清理顺序：先锁卡券，再软删除本人商品关联、清除旧绑定并按需归档卡券，
    最后保留原有商品目录缓存清理语义。共用卡券和全部卡密、关联历史均保留。

    Args:
        session: 数据库会话
        owner_id: 所属用户ID
        item_id: 闲鱼商品ID
    """
    if not item_id:
        return

    try:
        # 调用方历史上会捕获异常后提交；保存点避免提交半完成的卡券撤销。
        async with session.begin_nested():
            matcher = CardMatcher(session)
            locked_card_ids = await matcher._lock_item_cards([item_id], owner_id)
            legacy_cards = list((await session.execute(select(Card).where(
                Card.id.in_(locked_card_ids), Card.user_id == owner_id,
                Card.item_id == item_id, Card.is_deleted.is_(False),
            ).order_by(Card.id).with_for_update().execution_options(populate_existing=True))).scalars().all())
            legacy_ids = {card.id for card in legacy_cards}
            # 有效二级必有有效一级；先锁一级再锁关系，保护尚未绑定商品的分销并避免反锁。
            shared_ids = set((await session.execute(select(Card.id).join(
                DockRecord, DockRecord.card_id == Card.id,
            ).where(
                Card.id.in_(legacy_ids), DockRecord.level == 1, dock_access_condition(),
            ).order_by(DockRecord.id).with_for_update())).scalars().all())
            # 平台已确认删除时目录可能已经缺失；仍按 owner_id 撤销历史绑定，不放宽公共权限校验。
            await matcher._lock_item_relations([item_id], owner_id, locked_card_ids)
            relation_result = await session.execute(update(CardItemRelation).where(
                CardItemRelation.user_id == owner_id, CardItemRelation.item_id == item_id,
                CardItemRelation.is_deleted.is_(False),
            ).values(is_deleted=True))
            await matcher._clear_legacy([item_id], owner_id, locked_card_ids=locked_card_ids)

            # 当前锁读覆盖等卡锁期间提交的新关系；跨用户、暂不可用关系也保守保留卡密，
            # 此处仅决定是否归档，实际发货仍由公共 matcher 独立校验授权。
            shared_ids.update((await session.execute(select(CardItemRelation.card_id).where(
                CardItemRelation.card_id.in_(legacy_ids), CardItemRelation.is_deleted.is_(False),
            ).order_by(CardItemRelation.id).with_for_update())).scalars().all())
            card_count = 0
            for card in legacy_cards:
                if card.id not in shared_ids:
                    card.is_deleted = True
                    card.enabled = False
                    card_count += 1
            # 商品目录表的既有缓存清理行为不在本次卡券软删除迁移范围。
            item_result = await session.execute(delete(XYCatalogItem).where(
                XYCatalogItem.owner_id == owner_id, XYCatalogItem.item_id == item_id,
            ))
        logger.info(
            "商品删除同步完成: owner_id={}, item_id={}, relations_archived={}, cards_archived={}, "
            "shared_cards_preserved={}, catalog_records_removed={}",
            owner_id, item_id, relation_result.rowcount, card_count, len(shared_ids), item_result.rowcount,
        )
        # 外层事务仍由调用方提交，保存点不会提交调用方事务。
    except Exception:
        logger.exception("商品删除同步失败: owner_id={}, item_id={}", owner_id, item_id)
        raise
