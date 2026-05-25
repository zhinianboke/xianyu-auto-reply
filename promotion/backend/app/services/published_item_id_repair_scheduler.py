"""
返佣系统 - 发布后商品ID回写补偿定时任务

功能：
1. 定期检测素材库中已发布但发布后商品ID为空的数据
2. 通过素材中的随机字符（publish_random_str）匹配商品标题中的追踪码
3. 匹配成功后回写素材的 published_item_id
4. 回写成功后触发自动建卡流程
"""
from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.fy_material import FYMaterial, PUBLISH_STATUS_PUBLISHED
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem

# 定时任务间隔：3分钟
REPAIR_INTERVAL_SECONDS = 3 * 60
# 每批处理数量
REPAIR_BATCH_SIZE = 100

_repair_scheduler_running = False


async def run_published_item_id_repair_scheduler() -> None:
    """发布后商品ID回写补偿定时任务入口。"""
    logger.info("发布后商品ID回写补偿定时任务已启动，间隔: 3分钟")
    await asyncio.sleep(90)

    while True:
        try:
            await _repair_published_item_ids()
        except Exception as exc:
            logger.error(f"发布后商品ID回写补偿定时任务执行异常: {exc}")
        await asyncio.sleep(REPAIR_INTERVAL_SECONDS)


async def _repair_published_item_ids() -> None:
    """扫描已发布但 published_item_id 为空的素材，尝试通过追踪码匹配回写。"""
    global _repair_scheduler_running

    if _repair_scheduler_running:
        logger.info("发布后商品ID回写补偿定时任务正在执行中，跳过本次")
        return

    _repair_scheduler_running = True
    checked_count = 0
    repaired_count = 0
    skipped_count = 0
    failed_count = 0

    try:
        offset = 0
        while True:
            async with async_session_maker() as session:
                # 查询已发布但 published_item_id 为空、且有随机字符的素材
                stmt = (
                    select(
                        FYMaterial.id,
                        FYMaterial.owner_id,
                        FYMaterial.account_id,
                        FYMaterial.publish_random_str,
                    )
                    .where(
                        FYMaterial.publish_status == PUBLISH_STATUS_PUBLISHED,
                        or_(
                            FYMaterial.published_item_id.is_(None),
                            FYMaterial.published_item_id == "",
                        ),
                        FYMaterial.publish_random_str.is_not(None),
                        FYMaterial.publish_random_str != "",
                    )
                    .order_by(desc(FYMaterial.id))
                    .offset(offset)
                    .limit(REPAIR_BATCH_SIZE)
                )
                result = await session.execute(stmt)
                rows = result.all()

            if not rows:
                break

            offset += len(rows)
            for material_id, user_id, account_id, publish_random_str in rows:
                checked_count += 1
                trace_code = str(publish_random_str or "").strip()
                normalized_account_id = str(account_id or "").strip()

                if not trace_code:
                    skipped_count += 1
                    continue
                if not normalized_account_id:
                    skipped_count += 1
                    logger.warning(f"素材[{material_id}]缺少账号ID，跳过商品ID回写")
                    continue

                try:
                    published_item_id = await _find_item_id_by_trace_code(
                        user_id=int(user_id),
                        account_id=normalized_account_id,
                        trace_code=trace_code,
                    )
                    if not published_item_id:
                        skipped_count += 1
                        continue

                    # 回写 published_item_id
                    await _update_material_published_item_id(
                        material_id=material_id,
                        published_item_id=published_item_id,
                    )
                    repaired_count += 1
                    logger.info(
                        f"素材[{material_id}]通过追踪码[{trace_code}]匹配到商品ID[{published_item_id}]，已回写"
                    )

                    # 回写成功后触发自动建卡
                    await _trigger_auto_card(
                        material_id=material_id,
                        user_id=int(user_id),
                        published_item_id=published_item_id,
                    )
                except Exception as exc:
                    failed_count += 1
                    logger.warning(f"素材[{material_id}]商品ID回写异常: {exc}")

            if len(rows) < REPAIR_BATCH_SIZE:
                break

        if checked_count > 0:
            logger.info(
                f"发布后商品ID回写补偿定时任务执行完成: "
                f"检查{checked_count}条，修复{repaired_count}条，"
                f"跳过{skipped_count}条，失败{failed_count}条"
            )
    finally:
        _repair_scheduler_running = False


async def _find_item_id_by_trace_code(
    user_id: int,
    account_id: str,
    trace_code: str,
) -> str | None:
    """通过追踪码在商品标题中匹配，返回商品ID。"""
    trace_keyword = f"【{trace_code}】"
    async with async_session_maker() as session:
        stmt = (
            select(XYCatalogItem.item_id)
            .join(XYAccount, XYCatalogItem.account_pk == XYAccount.id)
            .where(
                XYAccount.owner_id == user_id,
                XYAccount.account_id == account_id,
                XYCatalogItem.title.like(f"%{trace_keyword}%"),
            )
            .order_by(
                desc(XYCatalogItem.updated_at),
                desc(XYCatalogItem.created_at),
                desc(XYCatalogItem.id),
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        item_id = result.scalars().first()
        if item_id:
            return str(item_id)
    return None


async def _update_material_published_item_id(
    material_id: int,
    published_item_id: str,
) -> None:
    """回写素材的发布后商品ID。"""
    async with async_session_maker() as session:
        stmt = select(FYMaterial).where(FYMaterial.id == material_id)
        result = await session.execute(stmt)
        material = result.scalar_one_or_none()
        if material:
            material.published_item_id = published_item_id
            await session.commit()


async def _trigger_auto_card(
    material_id: int,
    user_id: int,
    published_item_id: str,
) -> None:
    """回写成功后触发自动建卡流程。"""
    try:
        from app.services.publish_coupon_card_service import ensure_publish_coupon_card

        card_result = await ensure_publish_coupon_card(
            material_id=material_id,
            user_id=user_id,
            published_item_id=published_item_id,
        )
        if card_result.get("success"):
            logger.info(
                f"素材[{material_id}]商品ID回写后自动建卡完成: "
                f"card_id={card_result.get('card_id')}, "
                f"created={card_result.get('created')}, "
                f"updated={card_result.get('updated')}"
            )
        else:
            logger.warning(
                f"素材[{material_id}]商品ID回写后自动建卡跳过: {card_result.get('message', '')}"
            )
    except Exception as exc:
        logger.warning(f"素材[{material_id}]商品ID回写后自动建卡失败: {exc}")
