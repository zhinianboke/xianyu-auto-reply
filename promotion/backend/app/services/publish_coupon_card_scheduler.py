from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import desc, select

from common.db.session import async_session_maker
from common.models.fy_material import FYMaterial, PUBLISH_STATUS_PUBLISHED
from common.models.xy_catalog_item import XYCatalogItem

from app.services.publish_coupon_card_service import ensure_publish_coupon_card, get_publish_coupon_card_status

PUBLISH_COUPON_CARD_SCHEDULE_INTERVAL = 5 * 60
PUBLISH_COUPON_CARD_BATCH_SIZE = 100

_publish_coupon_card_scheduler_running = False


async def run_publish_coupon_card_scheduler() -> None:
    logger.info("发布卡券补偿定时任务已启动，间隔: 5分钟")
    await asyncio.sleep(60)

    while True:
        try:
            await _repair_publish_coupon_cards()
        except Exception as exc:
            logger.error(f"发布卡券补偿定时任务执行异常: {exc}")
        await asyncio.sleep(PUBLISH_COUPON_CARD_SCHEDULE_INTERVAL)


async def _load_existing_catalog_item_keys(rows: list[tuple[int, int, str | None]]) -> set[tuple[int, str]]:
    grouped_item_ids: dict[int, set[str]] = {}
    for _, user_id, published_item_id in rows:
        normalized_item_id = str(published_item_id or "").strip()
        if not normalized_item_id:
            continue
        grouped_item_ids.setdefault(int(user_id), set()).add(normalized_item_id)

    if not grouped_item_ids:
        return set()

    existing_keys: set[tuple[int, str]] = set()
    async with async_session_maker() as session:
        for owner_id, item_ids in grouped_item_ids.items():
            stmt = select(XYCatalogItem.owner_id, XYCatalogItem.item_id).where(
                XYCatalogItem.owner_id == owner_id,
                XYCatalogItem.item_id.in_(sorted(item_ids)),
            )
            result = await session.execute(stmt)
            for matched_owner_id, matched_item_id in result.all():
                existing_keys.add((int(matched_owner_id), str(matched_item_id or "").strip()))
    return existing_keys


async def _repair_publish_coupon_cards() -> None:
    global _publish_coupon_card_scheduler_running

    if _publish_coupon_card_scheduler_running:
        logger.info("发布卡券补偿定时任务正在执行中，跳过本次")
        return

    _publish_coupon_card_scheduler_running = True
    checked_count = 0
    repaired_count = 0
    skipped_count = 0
    failed_count = 0

    try:
        offset = 0
        while True:
            async with async_session_maker() as session:
                stmt = (
                    select(
                        FYMaterial.id,
                        FYMaterial.owner_id,
                        FYMaterial.published_item_id,
                    )
                    .where(
                        FYMaterial.publish_status == PUBLISH_STATUS_PUBLISHED,
                        FYMaterial.published_item_id.is_not(None),
                        FYMaterial.published_item_id != "",
                    )
                    .order_by(desc(FYMaterial.published_at), desc(FYMaterial.id))
                    .offset(offset)
                    .limit(PUBLISH_COUPON_CARD_BATCH_SIZE)
                )
                result = await session.execute(stmt)
                rows = result.all()

            if not rows:
                break

            existing_catalog_item_keys = await _load_existing_catalog_item_keys(rows)
            offset += len(rows)
            for material_id, user_id, published_item_id in rows:
                checked_count += 1
                normalized_item_id = str(published_item_id or "").strip()
                if not normalized_item_id:
                    skipped_count += 1
                    continue

                if (int(user_id), normalized_item_id) not in existing_catalog_item_keys:
                    skipped_count += 1
                    continue

                status = await get_publish_coupon_card_status(
                    material_id=material_id,
                    user_id=int(user_id),
                    published_item_id=normalized_item_id,
                )
                if status.get("success") and status.get("ready"):
                    skipped_count += 1
                    continue
                if not status.get("success"):
                    skipped_count += 1
                    continue

                try:
                    repair_result = await ensure_publish_coupon_card(
                        material_id=material_id,
                        user_id=int(user_id),
                        published_item_id=normalized_item_id,
                    )
                    if repair_result.get("success"):
                        if (
                            repair_result.get("created")
                            or repair_result.get("updated")
                            or repair_result.get("bind_success_count", 0) > 0
                        ):
                            repaired_count += 1
                        else:
                            skipped_count += 1
                    else:
                        failed_count += 1
                        logger.warning(
                            f"素材[{material_id}]发布卡券补偿失败: {repair_result.get('message', '')}"
                        )
                except Exception as exc:
                    failed_count += 1
                    logger.warning(f"素材[{material_id}]发布卡券补偿异常: {exc}")

            if len(rows) < PUBLISH_COUPON_CARD_BATCH_SIZE:
                break

        logger.info(
            f"发布卡券补偿定时任务执行完成: 检查{checked_count}条，修复{repaired_count}条，"
            f"跳过{skipped_count}条，失败{failed_count}条"
        )
    finally:
        _publish_coupon_card_scheduler_running = False
