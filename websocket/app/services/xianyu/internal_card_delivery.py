"""内部订单发货的当前卡券加载与配置校验，防止异步等待后使用旧内容。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.card import Card
from common.services.card_access import CardAccessError
from common.services.card_matcher import CardMatcher
from common.services.order_delivery_result import read_delivery_result
from common.db.query_conditions import not_deleted


def delivery_card_mode(card: Card) -> tuple[str, bool]:
    """提取影响发货步骤与数量策略的模式；参数为卡券，返回类型与表单开关。"""
    return card.type, bool(card.use_no_logistics_form)


async def load_authorized_delivery_card(
    session: AsyncSession,
    item_id: str,
    spec_name: str | None,
    spec_value: str | None,
    *,
    user_id: int,
    card_id: int,
    expected_binding: tuple[str, int] | None = None,
    expected_mode: tuple[str, bool] | None = None,
) -> tuple[Card, str, int]:
    """重读当前授权及卡券内容，拒绝来源或模式变化，允许同模式内容更新。

    Args:
        session: 调用方的独立短事务会话，不跨网络等待复用。
        item_id/spec_name/spec_value: 真实订单商品与规格。
        user_id/card_id: 真实订单所属用户与请求选中的卡券。
        expected_binding: 初次已验证的来源与对接编号，后续必须保持一致。
        expected_mode: 初次类型与表单开关，变化时不能沿用已经执行的发货步骤。
    Returns:
        当前完整卡券、已授权来源及规范化对接编号；校验失败抛出 CardAccessError。
    """
    cards = await CardMatcher(session).get_cards_by_item_id(
        item_id, spec_name, spec_value, user_id=user_id,
    )
    authorized = next((row for row in cards if row['id'] == card_id), None)
    if not authorized:
        raise CardAccessError("卡券不存在、已停用或未授权关联该订单商品")
    source = authorized.get('card_source') or 'own'
    dock_id = authorized.get('dock_record_id') or 0
    if expected_binding is not None and (source, dock_id) != expected_binding:
        raise CardAccessError("卡券关联来源已变更，已停止发货，请重新检查配置")
    card = (await session.execute(select(Card).where(
        Card.id == card_id, not_deleted(Card), Card.enabled.is_(True),
    ).execution_options(populate_existing=True))).scalars().first()
    if not card:
        raise CardAccessError("卡券已删除或停用，无法发货")
    if expected_mode is not None and delivery_card_mode(card) != expected_mode:
        raise CardAccessError("卡券类型或无需邮寄表单设置已变更，已停止发货，请重新检查配置")
    return card, source, dock_id


def configuration_failure_response(message: str, *, platform_shipping_confirmed: bool) -> dict:
    """生成未消费卡密的明确失败响应；如平台已确认，提示人工核实而不声称回滚。"""
    if platform_shipping_confirmed:
        message += "；平台已确认发货，但本次尚未发送卡券，请人工核实并补发"
    return {
        "success": False, "code": 40003, "message": message,
        "data": {"platform_shipping_confirmed": platform_shipping_confirmed, "quantity_sent": 0},
    }


def recorded_delivery_response(order_info: dict) -> dict | None:
    """回放已处理的配置中断结果，保留原数量与告警；普通历史订单返回 None。

    Args:
        order_info: 兼容层提供的真实订单快照，含元数据、平台状态与已保存卡券内容。
    Returns:
        不再消费卡券的幂等响应；没有已记录中断结果时返回 None。
    """
    result = read_delivery_result(order_info)
    if not result or not (result["delivery_incomplete"] or result["delivery_configuration_changed"] or result.get("agent_settlement_failed")):
        return None
    message = result.pop("message", None) or "该订单此前发货已中断，请人工核实已保存内容后补发"
    result.update({
        "order_no": order_info.get("order_no") or order_info.get("order_id") or result.get("order_no"),
        "content": order_info.get("delivery_content") or "",
        "already_delivery_processed": True,
    })
    if order_info.get("card_only_delivered"):
        result["already_card_only_delivered"] = True
    if str(order_info.get("status") or "").lower() in {"shipped", "completed"}:
        result["already_shipped"] = True
    settlement_failed = bool(result.get("agent_settlement_failed"))
    return {"success": not settlement_failed, "code": 40003 if settlement_failed else 200,
            "message": message, "data": result}
