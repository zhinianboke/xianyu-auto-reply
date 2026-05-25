"""
返佣系统 - 素材短连接回填补偿定时任务

功能：
1. 定期扫描素材库中 short_url 为空且存在推广链接的素材
2. 调用淘宝开放平台长链转短链接口补齐 short_url
3. 使用按素材ID游标分页，避免回填过程中漏扫未处理数据
4. 使用独立短会话回写结果，降低长时间持有数据库连接的风险
"""
from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy import and_, desc, or_, select

from common.db.session import async_session_maker
from common.models.fy_material import FYMaterial

SHORT_URL_REPAIR_INTERVAL_SECONDS = 10 * 60
SHORT_URL_REPAIR_BATCH_SIZE = 50

_short_url_repair_scheduler_running = False


async def run_material_short_url_repair_scheduler() -> None:
    """素材短连接回填补偿定时任务入口。"""
    logger.info("素材短连接回填补偿定时任务已启动，间隔: 10分钟")
    await asyncio.sleep(120)

    while True:
        try:
            await repair_material_short_urls_once()
        except Exception as exc:
            logger.error(f"素材短连接回填补偿定时任务执行异常: {exc}")
        await asyncio.sleep(SHORT_URL_REPAIR_INTERVAL_SECONDS)


async def repair_material_short_urls_once() -> None:
    """执行一次素材 short_url 回填。"""
    global _short_url_repair_scheduler_running

    if _short_url_repair_scheduler_running:
        logger.info("素材短连接回填补偿定时任务正在执行中，跳过本次")
        return

    _short_url_repair_scheduler_running = True
    checked_count = 0
    repaired_count = 0
    skipped_count = 0
    failed_count = 0
    last_material_id: int | None = None

    try:
        while True:
            rows = await _load_material_rows(last_material_id=last_material_id)
            if not rows:
                break

            last_material_id = int(rows[-1][0])
            for material_id, user_id, click_url, coupon_url in rows:
                checked_count += 1
                source_url = _resolve_source_url(click_url=click_url, coupon_url=coupon_url)
                if not source_url:
                    skipped_count += 1
                    continue

                try:
                    short_url, error_message = await _generate_short_url(user_id=int(user_id), source_url=source_url)
                    if not short_url:
                        failed_count += 1
                        logger.warning(
                            f"素材[{material_id}]短连接回填失败: {error_message or '未返回短连接'}"
                        )
                        continue

                    updated = await _update_material_short_url(
                        material_id=int(material_id),
                        short_url=short_url,
                    )
                    if updated:
                        repaired_count += 1
                        logger.info(f"素材[{material_id}]短连接回填成功: {short_url}")
                    else:
                        skipped_count += 1
                except Exception as exc:
                    failed_count += 1
                    logger.warning(f"素材[{material_id}]短连接回填异常: {exc}")

            if len(rows) < SHORT_URL_REPAIR_BATCH_SIZE:
                break

        logger.info(
            f"素材短连接回填补偿定时任务执行完成: 检查{checked_count}条，修复{repaired_count}条，"
            f"跳过{skipped_count}条，失败{failed_count}条"
        )
    finally:
        _short_url_repair_scheduler_running = False


async def _load_material_rows(last_material_id: int | None = None) -> list[tuple[int, int, str | None, str | None]]:
    """加载一批待回填短连接的素材。"""
    async with async_session_maker() as session:
        stmt = (
            select(
                FYMaterial.id,
                FYMaterial.owner_id,
                FYMaterial.click_url,
                FYMaterial.coupon_url,
            )
            .where(
                or_(FYMaterial.short_url.is_(None), FYMaterial.short_url == ""),
                or_(
                    and_(FYMaterial.coupon_url.is_not(None), FYMaterial.coupon_url != ""),
                    and_(FYMaterial.click_url.is_not(None), FYMaterial.click_url != ""),
                ),
            )
            .order_by(desc(FYMaterial.id))
            .limit(SHORT_URL_REPAIR_BATCH_SIZE)
        )
        if last_material_id is not None:
            stmt = stmt.where(FYMaterial.id < last_material_id)
        result = await session.execute(stmt)
        return result.all()


def _resolve_source_url(click_url: str | None, coupon_url: str | None) -> str:
    """优先使用券链接，其次使用推广链接。"""
    return str(coupon_url or "").strip() or str(click_url or "").strip()


async def _generate_short_url(user_id: int, source_url: str) -> tuple[str, str]:
    """生成素材短连接，失败返回错误消息。"""
    from app.services.taobao_alliance_detail import create_short_url

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            async with async_session_maker() as session:
                result = await create_short_url(
                    url=source_url,
                    session=session,
                    user_id=user_id,
                )
            if result.get("success") and result.get("data"):
                short_url = str(result["data"].get("short_url") or "").strip()
                if short_url:
                    return short_url, ""
                return "", "未返回短连接"
            return "", str(result.get("message") or "短连接生成失败")
        except Exception as exc:
            last_error = exc
            logger.warning(f"用户[{user_id}]短连接生成异常，第{attempt + 1}次重试: {exc}")
            await asyncio.sleep(1)

    if last_error:
        raise last_error
    return "", "短连接生成失败"


async def _update_material_short_url(material_id: int, short_url: str) -> bool:
    """回写素材 short_url，并同步补齐描述中的商品链接。"""
    normalized_short_url = str(short_url or "").strip()
    if not normalized_short_url:
        return False

    from app.services.product_rule_scheduler import merge_short_url_into_description

    async with async_session_maker() as session:
        stmt = select(FYMaterial).where(FYMaterial.id == material_id)
        result = await session.execute(stmt)
        material = result.scalar_one_or_none()
        if not material:
            return False
        if str(material.short_url or "").strip():
            return False
        material.short_url = normalized_short_url
        material.description = merge_short_url_into_description(material.description or "", normalized_short_url)
        await session.commit()
        return True
