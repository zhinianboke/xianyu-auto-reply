"""API关键词触发限制：查询真实成功日志及同买家同商品的有效订单数量。"""
from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import LargeBinary, cast, func, or_, select

from common.db.retry import with_db_retry
from common.db.session import async_session_maker
from common.models.auto_reply_message_log import XYAutoReplyMessageLog
from common.models.xy_order import XYOrder
from common.services.api_keyword_runtime import VALID_API_ORDER_STATUSES


def _success_scope(owner_id: int, account_id: str, buyer_id: str, item_id: str) -> list:
    """构建成功消息隔离条件；参数为用户、账号、买家及商品，返回SQL条件。"""
    if not owner_id or not account_id or not buyer_id:
        raise ValueError("缺少账号或买家信息，无法核对API关键词触发记录")
    return [
        XYAutoReplyMessageLog.owner_id == owner_id,
        XYAutoReplyMessageLog.account_id == account_id,
        XYAutoReplyMessageLog.sender_user_id == buyer_id,
        XYAutoReplyMessageLog.item_id == (item_id or None),
        XYAutoReplyMessageLog.process_status == "success",
        or_(XYAutoReplyMessageLog.send_status.is_(None),
            XYAutoReplyMessageLog.send_status.not_in(("failed", "timeout", "paused"))),
    ]


@with_db_retry()
async def check_api_keyword_trigger(
    config: dict[str, Any], account_id: str, buyer_id: str, item_id: str,
    message: str, matched_keyword: str,
) -> dict[str, Any]:
    """核对去重及订单额度，返回允许状态、中文原因和统计上下文。

    Args:
        config: 已匹配API规则快照，包含所属用户及两个触发开关。
        account_id: 真实闲鱼账号标识；buyer_id/item_id: 本次买家及商品。
        message: 完整原消息；matched_keyword: 本次实际命中的单个关键词。
    Returns:
        allowed为False时返回reason及message，context记录命中历史或订单统计。
    """
    context: dict[str, Any] = {}
    scope = _success_scope(config["owner_id"], account_id, buyer_id, item_id)
    async with async_session_maker() as session:
        try:
            if config.get("skip_same_message"):
                # 二进制比较保留大小写、尾部空格和完整内容，避免MySQL默认排序规则误去重。
                previous = (await session.execute(select(XYAutoReplyMessageLog.id).where(
                    *scope, cast(XYAutoReplyMessageLog.source_message, LargeBinary) == message.encode("utf-8"),
                ).limit(1))).scalar_one_or_none()
                if previous is not None:
                    context["api_keyword_previous_success_log_id"] = str(previous)
                    return {"allowed": False, "reason": "api_keyword_same_message",
                            "message": "相同消息已处理成功，本次不再触发", "context": context}
            if config.get("follow_order_quantity"):
                if not item_id or item_id == "未知商品":
                    return {"allowed": False, "reason": "api_keyword_order_quantity",
                            "message": "缺少商品信息，无法核对订单数量，本次不触发", "context": context}
                # 补录的历史订单可能最后入库，优先按真实下单时间选择最新订单。
                order = (await session.execute(select(
                    XYOrder.order_no, XYOrder.quantity, XYOrder.created_at, XYOrder.placed_at,
                ).where(
                    XYOrder.owner_id == config["owner_id"], XYOrder.account_id == account_id,
                    XYOrder.buyer_id == buyer_id, XYOrder.item_id == item_id,
                    XYOrder.status.in_(VALID_API_ORDER_STATUSES),
                ).order_by(func.coalesce(XYOrder.placed_at, XYOrder.created_at).desc(),
                           XYOrder.id.desc()).limit(1))).mappings().first()
                if order is None:
                    return {"allowed": False, "reason": "api_keyword_order_quantity",
                            "message": "没有该商品的有效订单，本次不触发", "context": context}
                quantity = order["quantity"]
                if not isinstance(quantity, int) or quantity < 1:
                    raise ValueError("订单购买数量无效，请同步订单后重试")
                if not matched_keyword:
                    raise ValueError("缺少命中的关键词，无法核对成功触发次数")
                count = (await session.execute(select(func.count()).select_from(XYAutoReplyMessageLog).where(
                    *scope, XYAutoReplyMessageLog.reply_strategy == "keyword",
                    XYAutoReplyMessageLog.matched_keyword == matched_keyword,
                    XYAutoReplyMessageLog.created_at >= (order["placed_at"] or order["created_at"]),
                ))).scalar_one()
                context.update(api_keyword_quantity_order_no=order["order_no"], api_keyword_order_quantity=quantity,
                               api_keyword_success_count=count, api_keyword_next_trigger_count=count + 1)
                if count + 1 > quantity:
                    return {"allowed": False, "reason": "api_keyword_order_quantity",
                            "message": "该关键词成功处理次数已达到订单购买数量，本次不再触发", "context": context}
            return {"allowed": True, "context": context}
        except Exception:
            await session.rollback()
            logger.exception("API关键词触发校验失败: account={}, buyer={}, item={}, rule_id={}",
                             account_id, buyer_id, item_id, config["id"])
            raise
