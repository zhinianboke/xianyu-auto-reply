"""
返佣系统 - 发布规则持久化服务

功能：
1. 使用独立短会话回写发布规则执行进度
2. 使用独立短会话回写素材发布成功结果
3. 在数据库连接短暂异常时进行有限重试
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime

from loguru import logger
from sqlalchemy import func, select

from common.db.session import async_session_maker
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.models.fy_material import FYMaterial, PUBLISH_STATUS_FAILED, PUBLISH_STATUS_PUBLISHED
from common.models.fy_publish_rule import FYPublishRule
from common.utils.time_utils import get_beijing_now_naive


async def save_publish_rule_progress(
    rule_id: int,
    today: date,
    today_count: int,
    last_run_at: datetime | None = None,
) -> None:
    """使用独立短会话回写发布规则进度。"""
    write_time = last_run_at or get_beijing_now_naive()
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            async with async_session_maker() as session:
                result = await session.execute(select(FYPublishRule).where(FYPublishRule.id == rule_id))
                rule = result.scalar_one_or_none()
                if not rule:
                    return
                rule.today_count = today_count
                rule.last_run_at = write_time
                rule.last_run_date = today
                await session.commit()
                return
        except Exception as exc:
            last_error = exc
            logger.warning(f"回写发布规则[{rule_id}]进度失败，第{attempt + 1}次重试: {exc}")
            await asyncio.sleep(1)
    if last_error:
        raise last_error


async def get_account_product_total_count(owner_id: int, account_id: str) -> int:
    account_id_str = str(account_id or "").strip()
    if not account_id_str:
        return 0
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            async with async_session_maker() as session:
                stmt = (
                    select(func.count())
                    .select_from(XYCatalogItem)
                    .join(XYAccount, XYCatalogItem.account_pk == XYAccount.id)
                    .where(
                        XYCatalogItem.owner_id == owner_id,
                        XYAccount.account_id == account_id_str,
                    )
                )
                result = await session.execute(stmt)
                return int(result.scalar() or 0)
        except Exception as exc:
            last_error = exc
            logger.warning(f"查询账号[{account_id_str}]商品总数失败，第{attempt + 1}次重试: {exc}")
            await asyncio.sleep(1)
    if last_error:
        raise last_error
    return 0


async def save_publish_failure(material_id: int) -> None:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            async with async_session_maker() as session:
                material_result = await session.execute(select(FYMaterial).where(FYMaterial.id == material_id))
                material = material_result.scalar_one_or_none()
                if not material:
                    raise ValueError(f"回写发布失败状态失败，素材[{material_id}]不存在")
                material.publish_status = PUBLISH_STATUS_FAILED
                material.published = False
                material.published_at = None
                material.published_item_id = None
                material.publish_random_str = None
                await session.commit()
                return
        except Exception as exc:
            last_error = exc
            logger.warning(f"回写素材[{material_id}]发布失败状态失败，第{attempt + 1}次重试: {exc}")
            await asyncio.sleep(1)
    if last_error:
        raise last_error


async def save_publish_success(
    rule_id: int,
    material_id: int,
    today: date,
    today_count: int,
    published_at: datetime,
    published_item_id: str | None,
    publish_random_str: str | None,
) -> None:
    """使用独立短会话回写素材发布成功结果和规则进度。"""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            async with async_session_maker() as session:
                rule_result = await session.execute(select(FYPublishRule).where(FYPublishRule.id == rule_id))
                rule = rule_result.scalar_one_or_none()
                material_result = await session.execute(select(FYMaterial).where(FYMaterial.id == material_id))
                material = material_result.scalar_one_or_none()
                if not rule or not material:
                    raise ValueError(f"回写发布结果失败，规则[{rule_id}]或素材[{material_id}]不存在")
                material.publish_status = PUBLISH_STATUS_PUBLISHED
                material.published = True
                material.published_at = published_at
                material.published_item_id = published_item_id or None
                material.publish_random_str = publish_random_str or None
                rule.today_count = today_count
                rule.last_run_at = published_at
                rule.last_run_date = today
                await session.commit()
                owner_id = int(material.owner_id)
                published_item_id_str = str(published_item_id or "").strip()
                if published_item_id_str:
                    try:
                        from app.services.publish_coupon_card_service import ensure_publish_coupon_card

                        card_result = await ensure_publish_coupon_card(
                            material_id=material_id,
                            user_id=owner_id,
                            published_item_id=published_item_id_str,
                        )
                        if card_result.get("success"):
                            logger.info(
                                f"素材[{material_id}]自动建卡完成: card_id={card_result.get('card_id')}, "
                                f"created={card_result.get('created')}, updated={card_result.get('updated')}"
                            )
                        else:
                            logger.warning(f"素材[{material_id}]自动建卡跳过: {card_result.get('message', '')}")
                    except Exception as card_exc:
                        logger.warning(f"素材[{material_id}]发布成功后自动建卡失败，不影响发布结果: {card_exc}")
                return
        except Exception as exc:
            last_error = exc
            logger.warning(f"回写素材[{material_id}]发布结果失败，第{attempt + 1}次重试: {exc}")
            await asyncio.sleep(1)
    if last_error:
        raise last_error
