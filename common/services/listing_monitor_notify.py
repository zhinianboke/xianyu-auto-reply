"""
商品监控采集结果通知

功能：
1. 监控任务开启「采集后通知」后，仅对本次新增商品推送通知
2. 推送到任务归属用户已启用的通知渠道（通知渠道页配置）
3. 支持 listing 模板与系统默认正文
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from common.db.session import async_session_maker
from common.models.notification_channel import NotificationChannel
from common.utils.notification_utils import send_to_notification_channels
from common.utils.xianyu_utils import canonical_goofish_item_url

# 单条通知正文最多展示的新增商品条数，超出部分用省略说明
_MAX_ITEMS_IN_MESSAGE = 10

_MONITOR_TYPE_LABELS = {
    "listing": "上新监控",
    "price_drop": "降价监控",
}


def _resolve_item_link(item: Dict[str, Any]) -> str:
    """解析通知用商品链接：优先可点击的 https 网页链接，避免 fleamarket:// 深链。"""
    item_id = (item.get("item_id") or "").strip()
    web_url = canonical_goofish_item_url(item_id)
    if web_url:
        return web_url

    target_url = (item.get("target_url") or "").strip()
    if target_url.lower().startswith(("http://", "https://")):
        return target_url
    return ""


def _build_items_summary(items: List[Dict[str, Any]]) -> str:
    """将新增商品列表格式化为通知正文中的摘要（含商品网页链接）。"""
    if not items:
        return "（无）"

    lines: List[str] = []
    for index, item in enumerate(items[:_MAX_ITEMS_IN_MESSAGE], start=1):
        title = (item.get("title") or "未知标题").strip() or "未知标题"
        price = (item.get("price") or "未知").strip() or "未知"
        item_id = (item.get("item_id") or "未知").strip() or "未知"
        area = (item.get("area") or "").strip()
        item_link = _resolve_item_link(item)
        line = f"{index}. {title}｜¥{price}｜ID:{item_id}"
        if area:
            line = f"{line}｜{area}"
        if item_link:
            line = f"{line}\n   链接: {item_link}"
        lines.append(line)

    omitted = len(items) - _MAX_ITEMS_IN_MESSAGE
    if omitted > 0:
        lines.append(f"... 另有 {omitted} 条未展示，请到后台「采集商品」查看")
    return "\n".join(lines)


def _build_default_message(
    *,
    keyword: str,
    monitor_type_label: str,
    task_id: int,
    account_id: Optional[str],
    inserted_count: int,
    fetched_count: int,
    items_summary: str,
    now_text: str,
) -> str:
    """构造系统默认通知正文。"""
    return (
        f"🆕 商品监控采集通知\n\n"
        f"监控关键字: {keyword}\n"
        f"监控类型: {monitor_type_label}\n"
        f"任务ID: {task_id}\n"
        f"采集账号: {account_id or '未知'}\n"
        f"本次获取: {fetched_count}\n"
        f"本次新增: {inserted_count}\n"
        f"时间: {now_text}\n\n"
        f"新增商品:\n{items_summary}\n"
    )


async def _load_owner_channels(owner_id: int) -> List[Dict[str, Any]]:
    """加载归属用户已启用的通知渠道。"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(NotificationChannel).where(
                NotificationChannel.owner_id == owner_id,
                NotificationChannel.enabled.is_(True),
            )
        )
        channels = list(result.scalars().all())
    return [
        {
            "id": channel.id,
            "name": channel.name,
            "channel_name": channel.name,
            "type": channel.channel_type,
            "channel_type": channel.channel_type,
            "config": channel.config_payload,
            "channel_config": channel.config_payload,
            "enabled": True,
        }
        for channel in channels
    ]


async def notify_listing_monitor_collect(
    *,
    owner_id: Optional[int],
    task_id: int,
    keyword: str,
    monitor_type: str,
    account_id: Optional[str],
    fetched_count: int,
    inserted_items: List[Dict[str, Any]],
) -> bool:
    """采集到新增商品后推送通知渠道。

    Args:
        owner_id: 监控任务归属用户；为空时跳过。
        task_id: 监控任务 ID。
        keyword: 监控关键字。
        monitor_type: listing / price_drop。
        account_id: 本次实际使用的主采集账号。
        fetched_count: 本次获取商品数。
        inserted_items: 本次新增商品摘要列表（至少含 item_id/title/price）。

    Returns:
        至少一个渠道发送成功时返回 True；未配置渠道或无可推送内容时返回 False。
    """
    inserted_count = len(inserted_items)
    if inserted_count <= 0:
        return False
    if owner_id is None:
        logger.warning(f"商品监控任务 {task_id} 无归属用户，跳过采集通知")
        return False

    try:
        channels = await _load_owner_channels(owner_id)
        if not channels:
            logger.info(
                f"商品监控任务 {task_id} 归属用户 {owner_id} 未配置启用通知渠道，跳过采集通知"
            )
            return False

        monitor_type_label = _MONITOR_TYPE_LABELS.get(monitor_type, monitor_type or "未知")
        items_summary = _build_items_summary(inserted_items)
        now_text = time.strftime("%Y-%m-%d %H:%M:%S")
        message = _build_default_message(
            keyword=keyword or "未知",
            monitor_type_label=monitor_type_label,
            task_id=task_id,
            account_id=account_id,
            inserted_count=inserted_count,
            fetched_count=fetched_count,
            items_summary=items_summary,
            now_text=now_text,
        )
        template_context = {
            "keyword": keyword or "未知",
            "monitor_type": monitor_type or "未知",
            "monitor_type_label": monitor_type_label,
            "task_id": str(task_id),
            "account_id": account_id or "未知",
            "inserted_count": str(inserted_count),
            "fetched_count": str(fetched_count),
            "items_summary": items_summary,
            "time": now_text,
        }

        sent = await send_to_notification_channels(
            channels,
            message,
            template_type="listing",
            template_context=template_context,
        )
        if sent:
            logger.info(
                f"商品监控任务 {task_id} 采集通知已发送："
                f"新增 {inserted_count} 条，渠道数 {len(channels)}"
            )
        else:
            logger.warning(f"商品监控任务 {task_id} 采集通知发送失败（渠道均未成功）")
        return sent
    except Exception as exc:  # noqa: BLE001
        logger.error(f"商品监控任务 {task_id} 采集通知异常: {exc}")
        return False
