"""卡券售罄自动下架守卫（stock guard）

触发语义：
- 对待发货订单（status ∈ {"待发货","pending","paid","pending_ship"}）按 quantity 求和，
  当总和 ≥ 卡券剩余库存（data_content 非空行数）时，自动下架该卡券绑定的所有商品。
- 仅 data（批量数据）类型且开启 auto_delist_on_soldout 的卡券生效。
- 所有入口函数均为尽力而为：任何异常只记日志，绝不抛出影响主流程。
"""
from __future__ import annotations

from typing import Any, Dict, List

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.card import Card
from common.models.notification_channel import NotificationChannel
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.models.xy_order import XYOrder
from common.services.card_matcher import CardMatcher
from common.services.item_offline_service import batch_offline_items_from_xianyu

PENDING_STATUSES = ("待发货", "pending", "paid", "pending_ship")


def _count_stock(card: Card) -> int:
    """data 卡剩余库存 = data_content 非空行数"""
    if not card.data_content:
        return 0
    return len([ln for ln in card.data_content.split("\n") if ln.strip()])


async def _pending_quantity(session: AsyncSession, item_ids: List[str]) -> int:
    if not item_ids:
        return 0
    stmt = select(func.coalesce(func.sum(XYOrder.quantity), 0)).where(
        XYOrder.item_id.in_(item_ids),
        XYOrder.status.in_(PENDING_STATUSES),
    )
    result = await session.execute(stmt)
    return int(result.scalar() or 0)


async def _bound_item_ids(session: AsyncSession, card: Card) -> List[str]:
    ids = await CardMatcher(session).get_card_item_ids(card.id)
    if card.item_id and card.item_id not in ids:  # legacy 单绑
        ids.append(card.item_id)
    return ids


async def _delist_items(session: AsyncSession, item_ids: List[str], card: Card) -> Dict[str, List[str]]:
    """按商品所属账号分组下架，返回 {"success": [...], "failed": [...]}"""
    result: Dict[str, List[str]] = {"success": [], "failed": []}
    if not item_ids:
        return result
    stmt = select(XYCatalogItem.item_id, XYAccount).join(
        XYAccount, XYAccount.id == XYCatalogItem.account_pk
    ).where(XYCatalogItem.item_id.in_(item_ids))
    rows = (await session.execute(stmt)).all()
    found_ids = {r[0] for r in rows}
    by_account: Dict[int, Dict[str, Any]] = {}
    for item_id, account in rows:
        slot = by_account.setdefault(account.id, {"account": account, "items": []})
        slot["items"].append(item_id)
    missing = [i for i in item_ids if i not in found_ids]
    if missing:
        logger.warning(f"[售罄下架] 以下商品不在商品库，跳过下架: {missing}")
        result["failed"].extend(missing)
    for slot in by_account.values():
        account: XYAccount = slot["account"]
        try:
            resp = await batch_offline_items_from_xianyu(
                account.account_id, account.cookie, slot["items"]
            )
            new_cookie = resp.get("cookies_str")
            if new_cookie and new_cookie != account.cookie:
                account.cookie = new_cookie
                await session.commit()
            for r in resp.get("results") or []:
                (result["success"] if r.get("success") else result["failed"]).append(r.get("item_id", ""))
            logger.info(
                f"[售罄下架] 卡券{card.id}({card.name}) 账号{account.account_id} 下架: "
                f"{resp.get('message')}"
            )
        except Exception as e:
            logger.error(f"[售罄下架] 账号{account.account_id} 下架异常: {e}")
            result["failed"].extend(slot["items"])
    return result


async def _notify_owner(session: AsyncSession, owner_id: int, message: str) -> None:
    """向用户所有启用的通知渠道发送告警（失败静默）"""
    try:
        channels = (
            await session.execute(
                select(NotificationChannel).where(
                    NotificationChannel.owner_id == owner_id,
                    NotificationChannel.enabled == True,  # noqa: E712
                )
            )
        ).scalars().all()
        if not channels:
            return
        from common.utils.notification_utils import (
            parse_notification_config, send_bark_notification, send_dingtalk_notification,
            send_email_notification, send_feishu_notification, send_pushplus_notification,
            send_telegram_notification, send_webhook_notification, send_wechat_notification,
        )
        for ch in channels:
            try:
                cfg = parse_notification_config(ch.config_payload)
                t = ch.channel_type
                if t in ("ding_talk", "dingtalk"):
                    await send_dingtalk_notification(cfg, message)
                elif t in ("feishu", "lark"):
                    await send_feishu_notification(cfg, message)
                elif t == "bark":
                    await send_bark_notification(cfg, message)
                elif t == "email":
                    await send_email_notification(cfg, message, None)
                elif t == "webhook":
                    await send_webhook_notification(cfg, message)
                elif t in ("wechat", "wechat_work"):
                    await send_wechat_notification(cfg, message)
                elif t == "pushplus":
                    await send_pushplus_notification(cfg, message)
                elif t == "telegram":
                    await send_telegram_notification(cfg, message)
            except Exception as e:
                logger.warning(f"[售罄下架] 通知渠道 {ch.id}({ch.channel_type}) 发送失败: {e}")
    except Exception as e:
        logger.warning(f"[售罄下架] 通知发送异常: {e}")


async def check_card_and_delist(
    session: AsyncSession, card_id: int, *, trigger: str
) -> Dict[str, Any]:
    """对单张卡执行售罄检查并按需下架。任何路径都不抛异常。"""
    try:
        card = (
            await session.execute(select(Card).where(Card.id == card_id))
        ).scalars().first()
        if not card or not card.enabled:
            return {"checked": False, "delisted": [], "reason": "card_missing_or_disabled"}
        if card.type != "data":
            return {"checked": False, "delisted": [], "reason": f"type_{card.type}_skipped"}
        if not card.auto_delist_on_soldout:
            return {"checked": False, "delisted": [], "reason": "switch_off"}

        stock = _count_stock(card)
        item_ids = await _bound_item_ids(session, card)
        pending = await _pending_quantity(session, item_ids)
        logger.info(
            f"[售罄下架] 检查 卡券{card.id}({card.name}) trigger={trigger} "
            f"stock={stock} pending={pending} items={item_ids}"
        )
        if pending < stock:
            return {"checked": True, "delisted": [], "reason": "below_threshold"}

        delist_result = await _delist_items(session, item_ids, card)
        ok_items = delist_result["success"]
        if ok_items:
            await _notify_owner(
                session, card.user_id,
                f"【售罄自动下架】卡券「{card.name}」库存{stock}张，待发货订单共{pending}张，"
                f"已达售罄阈值，已自动下架{len(ok_items)}个商品：{','.join(ok_items)}",
            )
        return {"checked": True, "delisted": ok_items, "failed": delist_result["failed"],
                "reason": "threshold_hit"}
    except Exception as e:
        logger.error(f"[售罄下架] check_card_and_delist({card_id}, {trigger}) 异常: {e}")
        return {"checked": False, "delisted": [], "reason": f"error:{e}"}


async def check_item_cards_after_order(
    session: AsyncSession, item_id: str, *, trigger: str
) -> None:
    """下单入库后：对该商品绑定的所有卡券执行检查。"""
    if not item_id:
        return
    try:
        matcher = CardMatcher(session)
        cards = await matcher.get_all_cards_by_item_id(item_id)
        for c in cards or []:
            cid = c.get("id") if isinstance(c, dict) else getattr(c, "id", None)
            if cid:
                await check_card_and_delist(session, int(cid), trigger=trigger)
    except Exception as e:
        logger.error(f"[售罄下架] check_item_cards_after_order({item_id}, {trigger}) 异常: {e}")


async def delist_card_if_empty(
    session: AsyncSession, card_id: int, *, trigger: str
) -> None:
    """发货完成后：data 卡库存归零时兜底下架（复用同一检查，stock=0 时必然命中阈值）。"""
    try:
        await check_card_and_delist(session, card_id, trigger=trigger)
    except Exception as e:
        logger.error(f"[售罄下架] delist_card_if_empty({card_id}, {trigger}) 异常: {e}")
