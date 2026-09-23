"""
AI 铺货任务执行器

功能：
1. 后台执行 AI 铺货任务：批量生成文案 → 可选生成图片 → 写入素材库
2. 逐条推进并写库，失败只影响当条，整体异常也会收尾任务状态
3. 控制并发与节流，支持用户中途取消（每条开始前检查任务状态）

说明：
- 由 FastAPI BackgroundTasks 调起，函数内部自建数据库会话，不复用请求会话。
- 同一个 AsyncSession 不能并发使用，因此图片生成可以并发、素材入库一律串行。
"""
from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, List

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.paths import get_upload_path
from app.services.ai_listing_config_service import AiListingConfigService
from app.services.ai_listing_task_service import AiListingTaskService
from app.services.ai_listing_text_generator import TEXT_BATCH_SIZE, generate_text_batch
from app.services.product_publish_service import ProductMaterialService
from common.db.session import async_session_maker
from common.models.ai_listing_config import AiListingConfig
from common.models.ai_listing_task import AiListingTask
from common.services.ai_image_client import (
    DEFAULT_IMAGE_TIMEOUT,
    SavedImage,
    cleanup_saved_images,
    generate_images,
)
from common.services.ai_text_client import DEFAULT_TEXT_TIMEOUT
from app.services.xianyu_item_snapshot import as_bool

# 图片生成的并发度（单任务内）与全局并发上限（跨任务）
IMAGE_CONCURRENCY = 3
_GLOBAL_IMAGE_SEMAPHORE = asyncio.Semaphore(6)

# 每处理一组素材后的节流间隔（秒）
THROTTLE_SECONDS = 1.0

def _resolve_price(raw_price: Any, params: Dict[str, Any]) -> float:
    """按用户选择的价格模式确定最终价格

    固定价模式直接用用户填的价；区间模式优先采用 AI 给的价格并夹到区间内，
    AI 没给有效价格时在区间内随机取值。最终价格不低于 0.01，
    避免四舍五入后出现 0 元素材（素材接口要求价格大于 0，否则后续编辑会校验失败）。

    Args:
        raw_price: AI 返回的价格。
        params: 任务参数快照。
    Returns:
        不小于 0.01 的最终价格（保留两位小数）。
    """
    if params.get("price_mode") == "fixed":
        return max(round(float(params.get("price") or 0.01), 2), 0.01)

    price_min = float(params.get("price_min") or 0.01)
    price_max = float(params.get("price_max") or price_min)
    try:
        price = float(raw_price)
    except (TypeError, ValueError):
        price = 0.0
    if price <= 0:
        price = random.uniform(price_min, price_max)
    price = min(max(price, price_min), price_max)
    return max(round(price, 2), 0.01)


async def _generate_item_images(
    client: httpx.AsyncClient,
    config: AiListingConfig,
    keyword: str,
    title: str,
) -> List[SavedImage]:
    """为单条素材生成图片（受全局并发闸门约束）

    Args:
        client: 复用的 httpx 客户端。
        config: AI 铺货配置。
        keyword: 生成主题。
        title: 素材标题，用于拼图片提示词。
    Returns:
        已落盘的图片列表。
    Raises:
        AiCallError: 图片接口调用失败或所有图片都无法落盘。
    """
    prompt = f"{title}，{keyword}，二手商品实拍图，背景干净，光线充足，高清细节"
    async with _GLOBAL_IMAGE_SEMAPHORE:
        return await generate_images(
            base_url=config.image_base_url or "",
            api_key=config.image_api_key or "",
            model=config.image_model or "",
            prompt=prompt,
            size=config.image_size or "1024x1024",
            count=int(config.image_count or 1),
            upload_dir=get_upload_path("products"),
            filename_prefix="ai",
            timeout=DEFAULT_IMAGE_TIMEOUT,
            client=client,
        )


def _build_material_data(
    item: Dict[str, Any],
    params: Dict[str, Any],
    image_urls: List[str],
    task_id: str,
) -> Dict[str, Any]:
    """把生成结果与素材默认值组装成素材库入库字段

    Args:
        item: 单条生成结果（title/description/price）。
        params: 任务参数快照。
        image_urls: 本条素材的图片地址列表。
        task_id: 任务ID，用于备注来源。
    Returns:
        可直接交给 ProductMaterialService.create 的字典。
    """
    defaults = params.get("material_defaults") or {}
    remark = (defaults.get("remark") or "").strip() or f"AI铺货生成（任务 {task_id[:8]}）"
    return {
        "title": item["title"],
        "description": item["description"],
        "price": _resolve_price(item.get("price"), params),
        "category": defaults.get("category"),
        "images": image_urls,
        "videos": [],
        "specifications": [],
        "sku_rows": [],
        "quantity": int(defaults.get("quantity") or 1),
        "delivery_method": "pickup" if (defaults.get("shipping_method") or "free") == "none" else "express",
        "shipping_method": defaults.get("shipping_method") or "free",
        "support_pickup": as_bool(defaults.get("support_pickup")),
        "postage": float(defaults.get("postage") or 0),
        "address": defaults.get("address"),
        "brand": defaults.get("brand"),
        "condition": defaults.get("condition") or "全新",
        "remark": remark[:500],
        "category_source": "manual",
    }


async def _save_material(
    session: AsyncSession,
    task_service: AiListingTaskService,
    *,
    owner_id: int,
    task_id: str,
    seq: int,
    item: Dict[str, Any],
    params: Dict[str, Any],
    images: List[SavedImage],
) -> None:
    """把单条生成结果写入素材库并更新明细状态

    入库失败时先回滚会话（否则同一 session 的后续写操作会抛 PendingRollbackError，
    导致任务无法收尾、永远停在执行中），再删除本条已落盘的图片，避免留下孤儿文件。
    """
    fallback_images = list((params.get("material_defaults") or {}).get("images") or [])
    image_urls = [image.url for image in images] or fallback_images
    if not image_urls:
        # 素材必须有图片，没有图片直接判失败，避免入库后无法发布
        cleanup_saved_images(images)
        await task_service.mark_item_failed(task_id, seq, "未获取到任何图片，且没有可用的兜底图片")
        return

    material_data = _build_material_data(item, params, image_urls, task_id)

    try:
        material = await ProductMaterialService(session).create(owner_id, material_data)
    except Exception as exc:
        await session.rollback()
        cleanup_saved_images(images)
        logger.error(f"【AI铺货】素材入库失败 task={task_id} seq={seq}：{exc}")
        await task_service.mark_item_failed(task_id, seq, f"素材入库失败：{exc}")
        return

    await task_service.mark_item_success(
        task_id,
        seq,
        title=item["title"],
        material_id=material.id,
        image_count=len(image_urls),
    )


async def _process_chunk(
    client: httpx.AsyncClient,
    session: AsyncSession,
    task_service: AiListingTaskService,
    *,
    config: AiListingConfig,
    params: Dict[str, Any],
    task_id: str,
    owner_id: int,
    keyword: str,
    entries: List[tuple[int, Dict[str, Any]]],
    image_enabled: bool,
) -> None:
    """处理一组素材：图片并发生成，素材串行入库

    素材入库必须串行（同一个 AsyncSession 不能并发使用），
    图片生成是纯 HTTP 调用，可以并发。
    """
    images_map: Dict[int, List[SavedImage]] = {}
    if image_enabled:
        results = await asyncio.gather(
            *[_generate_item_images(client, config, keyword, item["title"]) for _, item in entries],
            return_exceptions=True,
        )
        for (seq, _item), result in zip(entries, results):
            if isinstance(result, asyncio.CancelledError):
                # 进程关停等取消信号必须继续向上传播，不能当成普通失败
                raise result
            if isinstance(result, BaseException):
                message = getattr(result, "message", str(result))
                logger.warning(f"【AI铺货】图片生成失败 task={task_id} seq={seq}：{message}")
                await task_service.mark_item_failed(task_id, seq, f"图片生成失败：{message}")
                continue
            images_map[seq] = result

    for seq, item in entries:
        if image_enabled and seq not in images_map:
            # 图片失败已记账，跳过入库
            continue
        await _save_material(
            session,
            task_service,
            owner_id=owner_id,
            task_id=task_id,
            seq=seq,
            item=item,
            params=params,
            images=images_map.get(seq, []),
        )


def _resolve_image_enabled(config: AiListingConfig, params: Dict[str, Any]) -> bool:
    """确定本次任务是否生成图片

    任务参数可以覆盖配置开关；但图片接口地址/模型/密钥缺失时一律视为不启用。
    """
    override = params.get("image_enabled")
    enabled = bool(config.image_enabled) if override is None else bool(override)
    if not enabled:
        return False
    return bool(
        (config.image_base_url or "").strip()
        and (config.image_model or "").strip()
        and (config.image_api_key or "").strip()
    )


async def _execute_task(
    session: AsyncSession,
    task_service: AiListingTaskService,
    task: AiListingTask,
    config: AiListingConfig,
) -> None:
    """按批生成文案，再逐组生成图片并入库

    单批文案失败只让这批对应的明细失败，不影响后续批次；
    每组处理前都会检查任务是否已被取消。
    """
    params = task.params or {}
    task_id = task.task_id
    total = task.total_count or 0
    image_enabled = _resolve_image_enabled(config, params)
    timeout = max(DEFAULT_TEXT_TIMEOUT, DEFAULT_IMAGE_TIMEOUT)

    async with httpx.AsyncClient(timeout=timeout) as client:
        seq = 1
        while seq <= total:
            if await task_service.is_canceled(task_id):
                logger.info(f"【AI铺货】任务已被取消，停止执行 task={task_id}")
                await task_service.mark_remaining_items_canceled(task_id)
                return

            batch_size = min(TEXT_BATCH_SIZE, total - seq + 1)
            batch_seqs = list(range(seq, seq + batch_size))
            try:
                items = await generate_text_batch(client, config, params, task.keyword, batch_size)
            except Exception as exc:
                message = getattr(exc, "message", str(exc))
                logger.error(f"【AI铺货】文案生成失败 task={task_id} 起始序号={seq}：{message}")
                for failed_seq in batch_seqs:
                    await task_service.mark_item_failed(task_id, failed_seq, f"文案生成失败：{message}")
                seq += batch_size
                continue

            # AI 少返回的部分按失败记账，保证进度总数守恒
            for missing_seq in batch_seqs[len(items):]:
                await task_service.mark_item_failed(task_id, missing_seq, "AI未返回该条内容")

            entries = list(zip(batch_seqs, items))
            for start in range(0, len(entries), IMAGE_CONCURRENCY):
                if await task_service.is_canceled(task_id):
                    logger.info(f"【AI铺货】任务已被取消，停止执行 task={task_id}")
                    await task_service.mark_remaining_items_canceled(task_id)
                    return

                chunk = entries[start:start + IMAGE_CONCURRENCY]
                # 只把即将处理的这一组标记为执行中，避免取消后大量明细停在 running
                for running_seq, _item in chunk:
                    await task_service.mark_item_running(task_id, running_seq)

                await _process_chunk(
                    client,
                    session,
                    task_service,
                    config=config,
                    params=params,
                    task_id=task_id,
                    owner_id=task.owner_id,
                    keyword=task.keyword,
                    entries=chunk,
                    image_enabled=image_enabled,
                )
                await asyncio.sleep(THROTTLE_SECONDS)

            seq += batch_size


async def run_ai_listing_task(task_id: str) -> None:
    """后台任务入口：执行一次 AI 铺货

    自建数据库会话（不能复用请求会话），无论成功失败都会给任务收尾状态。

    Args:
        task_id: 任务ID（UUID）。
    """
    async with async_session_maker() as session:
        task_service = AiListingTaskService(session)
        task = await task_service.get_task(task_id)
        if not task:
            logger.warning(f"【AI铺货】任务不存在，已跳过 task={task_id}")
            return

        config = await AiListingConfigService(session).get(task.config_id, task.owner_id)
        if not config:
            logger.error(f"【AI铺货】配置不存在或已删除 task={task_id} config_id={task.config_id}")
            await task_service.mark_remaining_items_failed(
                task_id,
                "AI铺货配置不存在或已被删除",
            )
            await task_service.finish_task(task_id, "AI铺货配置不存在或已被删除")
            return

        logger.info(
            f"【AI铺货】开始执行任务 task={task_id} 条数={task.total_count} 主题={task.keyword}"
        )
        started = await task_service.mark_task_running(task_id)
        if not started:
            # 任务可能在后台执行器真正启动前已被取消，不能覆盖取消状态并继续生成。
            if await task_service.is_canceled(task_id):
                await task_service.mark_remaining_items_canceled(task_id)
            return
        try:
            await _execute_task(session, task_service, task, config)
        except Exception as exc:
            logger.error(f"【AI铺货】任务执行异常 task={task_id}：{exc}")
            # 先回滚，避免会话处于待回滚状态导致收尾写库继续失败
            await session.rollback()
            try:
                await task_service.mark_remaining_items_failed(task_id, f"任务执行异常：{exc}")
            except Exception as cleanup_exc:
                logger.error(f"【AI铺货】异常收尾明细失败 task={task_id}：{cleanup_exc}")
                await session.rollback()
            try:
                await task_service.finish_task(task_id, f"任务执行异常：{exc}")
            except Exception as finish_exc:
                logger.error(f"【AI铺货】任务收尾失败 task={task_id}：{finish_exc}")
            return

        try:
            await task_service.finish_task(task_id)
        except Exception as finish_exc:
            logger.error(f"【AI铺货】任务收尾失败 task={task_id}：{finish_exc}")
        logger.info(f"【AI铺货】任务执行结束 task={task_id}")


__all__ = ["run_ai_listing_task"]





