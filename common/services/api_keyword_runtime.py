"""API关键词运行数据访问：配置读取、下单资格及待发货订单核对、发货结果保存。"""
from __future__ import annotations

import re
from typing import Any

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.retry import with_db_retry
from common.db.session import async_session_maker
from common.models.xy_api_keyword_rule import XYApiKeywordRule
from common.models.xy_order import XYOrder
from common.utils.time_utils import get_beijing_now_naive

# pending/paid/中文状态兼容历史待发货订单；发货操作仍只允许待发货状态。
PENDING_DELIVERY_STATUSES = ("pending_ship", "pending", "paid", "待发货")
FULFILLED_ORDER_STATUSES = ("shipped", "completed")
# 下单资格及订单数量限制接受待发货、已发货、已完成，排除未付款、退款和关闭。
VALID_API_ORDER_STATUSES = (*PENDING_DELIVERY_STATUSES, *FULFILLED_ORDER_STATUSES)
CONFIG_FIELDS = (
    "id", "owner_id", "account_id", "url", "method", "timeout", "headers",
    "params", "response_field", "sync_confirm_delivery", "trigger_after_order",
    "follow_order_quantity", "skip_same_message",
)
ORDER_FIELDS = (
    "id", "owner_id", "account_id", "buyer_id", "item_id", "order_no",
    "status", "is_bargain", "card_only_delivered", "delivery_content",
    "metadata_json",
)
API_DELIVERY_METADATA_KEY = "api_keyword_delivery"


@with_db_retry()
async def list_api_keyword_rules(session: AsyncSession, owner_id: int, account_pk: int) -> list[dict[str, Any]]:
    """按所属用户及账号主键读取有效配置，返回可与普通关键词合并的快照。"""
    # 与普通关键词查询复用当前会话，避免每个消息同时占用两个连接。
    try:
        rules = (await session.scalars(
            select(XYApiKeywordRule).where(
                XYApiKeywordRule.owner_id == owner_id,
                XYApiKeywordRule.account_id == account_pk,
                XYApiKeywordRule.is_deleted.is_(False),
            ).order_by(XYApiKeywordRule.id)
        )).all()
    except Exception:
        await session.rollback()
        raise
    return [{
        "type": "api_keyword",
        "item_id": rule.item_id or "",
        "keyword": "\n".join(part.strip() for part in re.split(r"[,，\r\n]+", rule.keyword) if part.strip()),
        "api_config": {field: getattr(rule, field) for field in CONFIG_FIELDS},
    } for rule in rules]


def _order_scope(owner_id: int, account_id: str, buyer_id: str, item_id: str) -> tuple:
    """构造精确订单隔离条件；缺少身份或商品时拒绝扩大查询范围。"""
    if not owner_id or not account_id or not buyer_id or not item_id or item_id == "未知商品":
        raise ValueError("缺少买家或商品信息，无法核对订单")
    return (
        XYOrder.owner_id == owner_id,
        XYOrder.account_id == str(account_id),
        XYOrder.buyer_id == str(buyer_id),
        XYOrder.item_id == str(item_id),
    )


@with_db_retry()
async def get_pending_api_order(
    owner_id: int, account_id: str, buyer_id: str, item_id: str,
    order_id: int | None = None,
) -> dict[str, Any] | None:
    """读取同买家同商品最新待发货订单；指定主键时只重新核对该笔订单。"""
    scope = _order_scope(owner_id, account_id, buyer_id, item_id)
    return await _read_api_order(scope, order_id, PENDING_DELIVERY_STATUSES)


@with_db_retry()
async def get_api_confirmation_order(order: dict[str, Any]) -> dict[str, Any] | None:
    """只复核已发送结果的原订单，兼容免拼期间已同步为已发货/已完成；退款关闭仍拒绝。"""
    scope = _order_scope(order["owner_id"], order["account_id"], order["buyer_id"], order["item_id"])
    return await _read_api_order(scope, order["id"], VALID_API_ORDER_STATUSES)


@with_db_retry()
async def get_trigger_api_order(
    owner_id: int, account_id: str, buyer_id: str, item_id: str,
    order_id: int | None = None,
) -> dict[str, Any] | None:
    """读取符合下单资格的最新订单，不将触发资格用于放开发货状态限制。

    Args:
        owner_id: 所属系统用户ID。
        account_id: 闲鱼账号标识。
        buyer_id: 买家闲鱼用户ID。
        item_id: 当前商品ID。
        order_id: 可选的指定订单主键，复查时不切换到其他订单。
    Returns:
        同买家同商品的待发货、已发货或已完成订单；没有符合条件的订单时返回None。
    """
    scope = _order_scope(owner_id, account_id, buyer_id, item_id)
    return await _read_api_order(scope, order_id, VALID_API_ORDER_STATUSES)


async def _read_api_order(scope: tuple, order_id: int | None, statuses: tuple[str, ...]) -> dict[str, Any] | None:
    """在短会话中按固定隔离范围读取运行快照，不持有外部请求期间的事务。"""
    async with async_session_maker() as session:
        # 仅取运行字段，避免每次核对加载订单快照、地址和其他大字段。
        stmt = select(*(getattr(XYOrder, field) for field in ORDER_FIELDS)).where(
            *scope, XYOrder.status.in_(statuses),
        )
        if order_id is not None:
            stmt = stmt.where(XYOrder.id == order_id)
        order = (await session.execute(
            stmt.order_by(func.coalesce(XYOrder.placed_at, XYOrder.created_at).desc(),
                          XYOrder.id.desc()).limit(1)
        )).mappings().first()
        return dict(order) if order else None


@with_db_retry(retry_on_lock_contention=True)
async def save_api_order_checkpoint(
    order: dict[str, Any], rule_id: int, signature: str, content: str, send_checked: bool = False,
    sent_segments: list[int] | None = None,
) -> None:
    """持久化完整API结果及处理标记，保留待发货状态，重试复用结果并阻止普通自动发货重复取卡。"""
    scope = _order_scope(order["owner_id"], order["account_id"], order["buyer_id"], order["item_id"])
    async with async_session_maker() as session:
        try:
            current = (await session.scalars(select(XYOrder).where(
                *scope, XYOrder.id == order["id"],
                XYOrder.status.in_(PENDING_DELIVERY_STATUSES),
            ).with_for_update())).first()
            if current is None:
                raise ValueError("订单已不处于待发货状态，已停止API发货处理")
            metadata = dict(current.metadata_json or {})
            previous = metadata.get(API_DELIVERY_METADATA_KEY) or {}
            if previous and (previous.get("signature") != signature or previous.get("content") != content):
                raise ValueError("该订单已有其他API发货结果，请先核对原发货记录")
            if current.card_only_delivered and not previous:
                raise ValueError("该订单已由其他发货流程处理，请先核对发货记录")
            if not previous and str(current.delivery_content or "").strip():
                raise ValueError("该订单已有发货内容，请先核对原发货记录")
            metadata[API_DELIVERY_METADATA_KEY] = {
                "rule_id": rule_id, "signature": signature, "content": content,
                "send_checked": bool(send_checked or previous.get("send_checked")),
                "sent_segments": sorted(set(previous.get("sent_segments") or ()) | set(sent_segments or ())),
            }
            current.metadata_json = metadata
            current.card_only_delivered = True
            # 处理中内容仅保存在元数据；正式字段由确认成功后写入，避免提前触发自动续售。
            current.updated_at = get_beijing_now_naive()
            await session.commit()
            logger.info("API关键词结果已持久化: order_no={}, rule_id={}, send_checked={}",
                        order["order_no"], rule_id, send_checked)
        except Exception:
            await session.rollback()
            logger.exception("API关键词结果持久化失败: order_no={}", order["order_no"])
            raise


@with_db_retry(retry_on_lock_contention=True)
async def save_api_order_delivery(order: dict[str, Any], content: str, error: str | None = None) -> None:
    """保存指定隔离范围订单的发货结果，成功才转为已发货；允许断线后幂等重试。"""
    scope = _order_scope(order["owner_id"], order["account_id"], order["buyer_id"], order["item_id"])
    async with async_session_maker() as session:
        try:
            values: dict[str, Any] = {"delivery_fail_reason": error[:2000] if error else None}
            if error is None:
                values.update(status="shipped", delivery_method="auto", delivery_content=content[:2000])
            values["updated_at"] = get_beijing_now_naive()
            result = await session.execute(update(XYOrder).where(
                *scope, XYOrder.id == order["id"],
                XYOrder.status.in_(PENDING_DELIVERY_STATUSES),
            ).values(**values))
            if error is None and result.rowcount == 0:
                # 平台成功时可能已有同步任务先更新状态，补齐内容并保留已完成状态。
                existing = await session.execute(update(XYOrder).where(
                    *scope, XYOrder.id == order["id"], XYOrder.status.in_(("shipped", "completed")),
                ).values(delivery_method="auto", delivery_content=content[:2000], delivery_fail_reason=None))
                if existing.rowcount == 0:
                    raise ValueError("平台确认已返回成功，但本地订单状态已变化，请核对订单")
            await session.commit()
            logger.info("API关键词订单结果保存: order_no={}, result={}", order["order_no"], error or "已发货")
        except Exception:
            await session.rollback()
            logger.exception("API关键词订单结果保存失败: order_no={}", order["order_no"])
            raise
