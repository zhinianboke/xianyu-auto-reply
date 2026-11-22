"""已取对接卡券的结算审计：保留恢复线索，不重发卡券或自动重复扣款。"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial
from uuid import uuid4

from loguru import logger
from sqlalchemy import select

from common.db.session import async_session_maker
from common.models.xy_order import XYOrder

SETTLEMENT_RESULT_KEY = "agent_settlement_result"


class AgentSettlementCommitUncertainError(RuntimeError):
    """财务提交结果不确定；必须保留 pending 审计并人工查流水，禁止自动重试。"""


def read_settlement_result(order_or_metadata) -> dict | None:
    """读取订单或元数据中的真实结算审计；无有效记录时返回 None。"""
    metadata = (order_or_metadata.get("metadata_json", order_or_metadata)
                if isinstance(order_or_metadata, dict)
                else getattr(order_or_metadata, "metadata_json", None))
    result = metadata.get(SETTLEMENT_RESULT_KEY) if isinstance(metadata, dict) else None
    if not isinstance(result, dict) or not isinstance(result.get("status"), str):
        return None
    return dict(result) if result["status"] in {"pending", "failed", "settled"} else None


async def _save_settlement_result(order_no: str, owner_id: int, result: dict,
                                   *, clear_delivery_pending: bool = False) -> None:
    """锁读合并订单结算审计，保留其他元数据；失败抛异常给调用方明确处理。"""
    if (not isinstance(result.get("status"), str) or result["status"] not in {"pending", "failed", "settled"}
            or not isinstance(result.get("attempt_id"), str) or not result["attempt_id"]):
        raise ValueError("结算审计缺少有效状态或处理标识")
    async with async_session_maker() as session:
        order = (await session.execute(select(XYOrder).where(
            XYOrder.order_no == order_no, XYOrder.owner_id == owner_id,
        ).with_for_update().execution_options(populate_existing=True))).scalars().first()
        if order is None:
            raise ValueError("订单不存在或归属不一致，无法保存结算审计")
        metadata = dict(order.metadata_json or {})
        previous = read_settlement_result(metadata)
        if (result["status"] == "pending" and isinstance(previous, dict)
                and previous.get("status") in {"pending", "failed", "settled"}
                and previous.get("attempt_id") != result.get("attempt_id")):
            raise ValueError("该订单已有结算审计，请人工核实已有代理订单和流水，禁止自动重复结算")
        metadata[SETTLEMENT_RESULT_KEY] = result
        if result["status"] == "settled" and clear_delivery_pending:
            delivery = metadata.get("delivery_result")
            if isinstance(delivery, dict):
                delivery = dict(delivery)
                delivery["agent_settlement_failed"] = False
                if not delivery.get("delivery_configuration_changed") and not delivery.get("delivery_incomplete"):
                    delivery["message"] = "发货及代理结算已完成"
                metadata["delivery_result"] = delivery
        order.metadata_json = metadata
        if result["status"] == "failed":
            reason = result["message"]
            if reason not in (order.delivery_fail_reason or ""):
                order.delivery_fail_reason = "；".join(filter(None, (order.delivery_fail_reason, reason)))
        await session.commit()


async def settle_consumed_delivery(
    *, order_no: str, owner_id: int, item_id: str, card_id: int, dock_record_id: int,
    create_agent_order: Callable[[], Awaitable[dict]],
    clear_delivery_pending: bool = False,
) -> dict:
    """审计已耗卡结算并返回真实结果；创建失败仍保留订单、卡券和代理记录线索。

    调用方已持有订单发货锁。本方法不消费库存、不重新发卡、不自动重试财务操作。
    clear_delivery_pending 为 True 时，成功审计与解除临时防续售标记同事务提交。
    返回 success/message/agent_order_id/audit_saved；提交不确定时保留 pending 供人工核验。
    """
    audit = {
        "order_no": order_no, "owner_id": owner_id, "item_id": item_id,
        "card_id": card_id, "dock_record_id": dock_record_id, "status": "pending",
        "attempt_id": uuid4().hex,
        "message": "卡券已取出，代理结算处理中；请勿重复发卡",
    }
    audit_error = None
    try:
        await _save_settlement_result(order_no, owner_id, audit, clear_delivery_pending=clear_delivery_pending)
    except Exception as error:
        audit_error = str(error)
        logger.opt(exception=error).error("已耗卡结算前审计保存失败: result={}", audit)
        return {"success": False, "message": (
            f"卡券已取出，但结算前审计保存失败：{error}；本次未执行结算，请人工核实，勿重复发卡"
        ), "audit_saved": False}
    try:
        result = await create_agent_order()
        if isinstance(result, dict):
            audit["agent_order_id"] = result.get("agent_order_id")
        if not isinstance(result, dict) or result.get("success") is not True:
            message = result.get("message") if isinstance(result, dict) else None
            raise RuntimeError(message or "代理结算未返回明确成功结果")
        audit.update(status="settled", agent_order_id=result.get("agent_order_id"), message="代理结算成功")
    except AgentSettlementCommitUncertainError as error:
        audit.update(message=f"代理结算提交结果不确定：{error}；请人工核实代理订单和资金流水，勿重复发卡或直接重试扣款")
        logger.opt(exception=error).error("已耗卡结算提交结果不确定: result={}", audit)
    except Exception as error:
        audit.update(status="failed", message=(
            f"卡券已取出，但代理结算失败：{error}；请人工核实代理订单和资金流水，勿重复发卡或直接重试扣款"
        ))
        logger.opt(exception=error).error("已耗卡代理结算失败: result={}", audit)
    try:
        await _save_settlement_result(order_no, owner_id, audit, clear_delivery_pending=clear_delivery_pending)
        audit_error = None
    except Exception as error:
        audit_error = str(error)
        logger.opt(exception=error).error("已耗卡结算结果审计保存失败: result={}", audit)
    if audit_error:
        return {"success": False, "message": (
            f"{audit['message']}；结算审计保存失败：{audit_error}；请立即人工核实，勿重复发卡或直接重试扣款"
        ), "agent_order_id": audit.get("agent_order_id"), "audit_saved": False}
    return {"success": audit["status"] == "settled", "message": audit["message"],
            "agent_order_id": audit.get("agent_order_id"), "audit_saved": True}


async def settle_agent_deliveries(handler, *, order_no: str, item_id: str, buyer_id: str,
                                  owner_id: int, deliveries: list[tuple[dict, str]]) -> str | None:
    """结算调用方已保存内容的对接卡券；返回完整错误提示，无错误返回 None。"""
    errors = []
    for card, content in deliveries:
        result = await settle_consumed_delivery(
            order_no=order_no, owner_id=owner_id, item_id=item_id,
            card_id=card["id"], dock_record_id=card["dock_record_id"],
            create_agent_order=partial(handler._create_agent_order, order_id=order_no,
                                       item_id=item_id, card=card, delivery_content=content, buyer_id=buyer_id),
        )
        if not result["success"]:
            errors.append(result["message"])
            break  # 待恢复结算只能人工核验，禁止自动再创建或扣款。
    return "；".join(errors) if errors else None


async def record_and_settle_agent_deliveries(handler, *, order_no: str, item_id: str,
                                             buyer_id: str, owner_id: int, content: str,
                                             record_content: Callable[[], Awaitable[bool]],
                                             deliveries: list[tuple[dict, str]]) -> str | None:
    """先保存已取卡内容和防重状态，再结算；任何保存失败均禁止开始财务操作。"""
    try:
        if not await record_content():
            raise RuntimeError("已取卡内容和防重状态未能保存")
    except Exception as error:
        logger.opt(exception=error).error("结算前保存已取卡内容失败: order_no={}, content={}", order_no, content)
        return f"卡券已取出，但内容和防重记录保存失败：{error}；本次未执行结算，请立即人工核实，勿重复发卡"
    return await settle_agent_deliveries(handler, order_no=order_no, item_id=item_id,
                                         buyer_id=buyer_id, owner_id=owner_id, deliveries=deliveries)
