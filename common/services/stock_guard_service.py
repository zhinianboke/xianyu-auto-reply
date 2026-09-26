"""卡券售罄自动下架守卫（stock guard）

触发语义：
- 对待发货订单（status ∈ {"待发货","pending","paid","pending_ship"}）按 quantity 求和，
  当总和 ≥ 卡券剩余库存（data_content 非空行数）时，自动下架该卡券绑定的所有商品。
- 仅 data（批量数据）类型且开启 auto_delist_on_soldout 的卡券生效。
- 卡券带规格（spec_name/spec_value 均非空）时，待发货订单按同规格过滤（D0-27 ②）；
  卡券规格为空（单规格商品/旧数据）时退化为只按 item_id 统计，与历史行为一致。
- data_content 为空/None 时用 delivery_count（累计发货次数，只增不减）区分（D0-27 ③ + F8b）：
  · delivery_count > 0 = 曾配置卡密且已被消耗光 → 视为「售罄」，继续走阈值判定与下架流程；
  · delivery_count == 0 = 从未配置过卡密 → 不参与阈值判定、不下架（reason=no_stock_data）。
- 卡券带规格且命中阈值时，不得因这一张规格卡售罄就把整个商品下架（D0-27 ④）：
  仅当同一商品下查不到其它带规格卡券（已无其它规格可售）才按原流程整品下架；查到其它
  规格卡券、或规格查询失败时不下架，告警并通知卖家手动处理
  （reason=spec_soldout_no_delist，查询失败按 fail-safe 保守不下架）。
- 所有入口函数均为尽力而为：任何异常只记日志，绝不抛出影响主流程。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from loguru import logger
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.card import Card
from common.models.card_item_relation import CardItemRelation
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


async def _pending_quantity(
    session: AsyncSession, item_ids: List[str], card: Card | None = None
) -> int:
    """统计待发货订单数量（SUM(quantity)）。

    卡券 spec_name/spec_value 均非空时按「item_id + spec_name + spec_value」过滤，
    避免其它规格的待发货订单算进本卡阈值；任一为空（单规格商品/旧数据）时不加规格
    条件，保持原行为（D0-27 ②）。
    """
    if not item_ids:
        return 0
    conditions = [
        XYOrder.item_id.in_(item_ids),
        XYOrder.status.in_(PENDING_STATUSES),
    ]
    spec_name = (card.spec_name or "").strip() if card is not None else ""
    spec_value = (card.spec_value or "").strip() if card is not None else ""
    if spec_name and spec_value:
        conditions.append(XYOrder.spec_name == spec_name)
        conditions.append(XYOrder.spec_value == spec_value)
    stmt = select(func.coalesce(func.sum(XYOrder.quantity), 0)).where(*conditions)
    result = await session.execute(stmt)
    return int(result.scalar() or 0)


async def _bound_item_ids(session: AsyncSession, card: Card) -> List[str]:
    ids = await CardMatcher(session).get_card_item_ids(card.id)
    if card.item_id and card.item_id not in ids:  # legacy 单绑
        ids.append(card.item_id)
    return ids


async def _other_spec_cards(
    session: AsyncSession, card: Card, item_ids: List[str]
) -> Tuple[bool, bool, List[str]]:
    """查询同一商品下是否还存在「其它带规格卡券」（D0-27 ④）。

    返回 `(has_other, query_ok, specs)`：
    - `has_other`：查到其它带规格卡券 → 该商品仍有其它规格在售，不得整品下架；
    - `query_ok`：查询是否成功。False 时调用方必须**保守地不下架**（fail-safe）；
    - `specs`：其它规格描述（`规格名=规格值`），用于日志与通知文案。

    查询来源与 `_bound_item_ids` 的双来源保持一致：优先 `xy_card_item_relations`
    （关联表），并覆盖 legacy 单绑字段 `xy_cards.item_id`；排除卡券自身；
    仅取 `spec_name` 非空的卡券；不过滤 enabled（禁用卡券对应的规格在平台上仍可售，
    保守判定不下架更安全）。
    """
    if not item_ids:
        return False, True, []
    try:
        related_card_ids = select(CardItemRelation.card_id).where(
            CardItemRelation.item_id.in_(item_ids)
        )
        stmt = select(Card.spec_name, Card.spec_value).where(
            or_(Card.id.in_(related_card_ids), Card.item_id.in_(item_ids)),
            Card.id != card.id,
            Card.spec_name.isnot(None),
            Card.spec_name != "",
        )
        rows = (await session.execute(stmt)).all()
    except Exception as e:
        logger.error(
            f"[售罄下架] 查询其它规格卡券失败（保守处理：不下架）: card={card.id}, "
            f"items={item_ids}, error={type(e).__name__}: {e}"
        )
        return False, False, []
    specs: List[str] = []
    for spec_name, spec_value in rows:
        name = str(spec_name or "").strip()
        if not name:
            continue
        value = str(spec_value or "").strip()
        label = f"{name}={value}" if value else name
        if label not in specs:
            specs.append(label)
    return bool(specs), True, specs


async def _persist_refreshed_cookie(account_pk: int, cookie: str) -> None:
    """把下架接口刷新后的 Cookie 写回账号（D0-29）。

    使用独立 session：既不提交调用方传入的事务（不破坏调用方事务边界），
    也不受调用方后续 rollback 影响（此前直接在调用方 session 上 commit）。
    """
    try:
        from common.db.session import async_session_maker

        async with async_session_maker() as _session:
            await _session.execute(
                update(XYAccount).where(XYAccount.id == account_pk).values(cookie=cookie)
            )
            await _session.commit()
    except Exception as e:
        logger.warning(f"[售罄下架] 刷新Cookie写回失败（忽略）: account_pk={account_pk}, error={e}")


async def _delist_items(session: AsyncSession, item_ids: List[str], card: Card) -> Dict[str, List[str]]:
    """按商品所属账号分组下架，返回 {"success": [...], "failed": [...], "reasons": [...]}"""
    result: Dict[str, List[str]] = {"success": [], "failed": [], "reasons": []}
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
        result["reasons"].extend([f"{i}: 商品不在商品库（所属账号可能已删除）" for i in missing])
    for slot in by_account.values():
        account: XYAccount = slot["account"]
        try:
            resp = await batch_offline_items_from_xianyu(
                account.account_id, account.cookie, slot["items"]
            )
            new_cookie = resp.get("cookies_str")
            if new_cookie and new_cookie != account.cookie:
                # 写回刷新后的 Cookie：走独立 session，不污染调用方事务
                await _persist_refreshed_cookie(account.id, new_cookie)
            fail_message = str(resp.get("message") or "下架接口返回失败")
            for r in resp.get("results") or []:
                if r.get("success"):
                    result["success"].append(r.get("item_id", ""))
                else:
                    failed_id = r.get("item_id", "")
                    result["failed"].append(failed_id)
                    result["reasons"].append(f"{failed_id}: {fail_message}")
            logger.info(
                f"[售罄下架] 卡券{card.id}({card.name}) 账号{account.account_id} 下架: "
                f"{resp.get('message')}"
            )
        except Exception as e:
            logger.error(f"[售罄下架] 账号{account.account_id} 下架异常: {e}")
            result["failed"].extend(slot["items"])
            result["reasons"].extend(
                [f"{i}: 下架异常 {type(e).__name__}: {e}" for i in slot["items"]]
            )
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
        # 区分「未配置卡密」与「已配置且已耗尽（售罄）」（D0-27 ③ + F8b）：
        # data_content 为空/None 时二者不可区分，改用 delivery_count（xy_cards 累计发货次数，
        # 只增不减、无任何重置点：写入点仅 common/db/compat.py:1641 的 increment_delivery_count，
        # 由 internal.py 与 auto_delivery_handler.py 的发货路径调用）作为「曾经配置过」的信号：
        #   - delivery_count > 0：曾配置卡密并已发出，库存已被消耗光 → 按「售罄」继续走阈值判定；
        #   - delivery_count == 0：从未配置过卡密（无任何发货记录）→ 不参与售罄判定、不下架。
        if not card.data_content or not str(card.data_content).strip():
            if (card.delivery_count or 0) > 0:
                logger.warning(
                    f"[售罄下架] 卡券{card.id}({card.name}) 卡密已耗尽（data_content 为空，"
                    f"历史发货{card.delivery_count}次）→ 按「售罄」继续阈值判定: trigger={trigger}"
                )
            else:
                logger.warning(
                    f"[售罄下架] 卡券{card.id}({card.name}) 未配置卡密（data_content 为空且"
                    f"delivery_count=0），不参与售罄判定: trigger={trigger}"
                )
                return {"checked": False, "delisted": [], "reason": "no_stock_data"}

        item_ids = await _bound_item_ids(session, card)
        pending = await _pending_quantity(session, item_ids, card)
        logger.info(
            f"[售罄下架] 检查 卡券{card.id}({card.name}) trigger={trigger} "
            f"stock={stock} pending={pending} items={item_ids} "
            f"spec={card.spec_name or ''}:{card.spec_value or ''}"
        )
        if pending < stock:
            return {"checked": True, "delisted": [], "reason": "below_threshold"}

        spec_name = (card.spec_name or "").strip()
        spec_value = (card.spec_value or "").strip()
        if spec_name and spec_value:
            # D0-27 ④：规格卡售罄不得把整个商品下架（商品通常还有其它规格在售）。
            # 判定依据：同一商品下是否还存在其它带规格卡券；查询失败按 fail-safe 保守不下架。
            has_other, query_ok, other_specs = await _other_spec_cards(session, card, item_ids)
            if not query_ok or has_other:
                spec_label = f"{spec_name}={spec_value}"
                if not query_ok:
                    detail = "的其它规格卡券查询失败（保守处理）"
                else:
                    detail = f"仍有其它规格在售（{'、'.join(other_specs)}）"
                logger.warning(
                    f"[售罄下架] 卡券{card.id}({card.name}) 规格[{spec_label}]已达售罄阈值"
                    f"（stock={stock} pending={pending} items={item_ids}），但该商品{detail}，"
                    f"未自动下架整品（reason=spec_soldout_no_delist）: trigger={trigger}"
                )
                await _notify_owner(
                    session,
                    card.user_id,
                    f"【售罄未下架】规格「{spec_label}」的卡券「{card.name}」已售罄"
                    f"（剩余库存{stock}张，待发货订单{pending}张），"
                    f"商品{'、'.join(item_ids) or '（未知商品）'}{detail}，未自动下架，"
                    f"请手动处理（补卡密或手动下架该商品）。",
                )
                return {
                    "checked": True,
                    "delisted": [],
                    "failed": [],
                    "reason": "spec_soldout_no_delist",
                    "other_specs": other_specs,
                }
            logger.warning(
                f"[售罄下架] 卡券{card.id}({card.name}) 规格[{spec_name}={spec_value}]已售罄，"
                f"且商品{item_ids}下未发现其它规格卡券（无其它规格可售），按原流程整品下架: "
                f"trigger={trigger}"
            )

        delist_result = await _delist_items(session, item_ids, card)
        ok_items = delist_result["success"]
        failed_items = delist_result["failed"]
        if failed_items:
            # 5 个调用点全部丢弃返回值，失败必须在此留痕（error 级 + 原因）
            logger.error(
                f"[售罄下架] 卡券{card.id}({card.name}) trigger={trigger} "
                f"下架失败{len(failed_items)}个商品: {failed_items}；"
                f"失败原因: {delist_result.get('reasons')}"
            )
        if ok_items or failed_items:
            parts = [
                f"【售罄自动下架】卡券「{card.name}」库存{stock}张，待发货订单共{pending}张，"
                f"已达售罄阈值"
            ]
            if ok_items:
                parts.append(f"已自动下架{len(ok_items)}个商品：{','.join(ok_items)}")
            if failed_items:
                parts.append(
                    f"下架失败{len(failed_items)}个商品（请手动处理）：{','.join(failed_items)}"
                )
            await _notify_owner(session, card.user_id, "，".join(parts) + "。")
        return {"checked": True, "delisted": ok_items, "failed": failed_items,
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
    """发货完成后：对 data 卡复用同一套阈值检查兜底下架。

    注意（D0-27 ③ + F8b）：data_content 为空时用 delivery_count 区分——曾配置过卡密
    （delivery_count > 0）按「售罄」继续判定，从未配置（delivery_count == 0）不参与判定、
    不会下架；实际触发下架的条件是「待发货订单数 ≥ 剩余库存且（剩余库存 > 0 或已耗尽）」。
    带规格的卡券命中阈值时按 D0-27 ④ 不整品下架（除非该商品已无其它规格卡券）。
    """
    try:
        await check_card_and_delist(session, card_id, trigger=trigger)
    except Exception as e:
        logger.error(f"[售罄下架] delist_card_if_empty({card_id}, {trigger}) 异常: {e}")
