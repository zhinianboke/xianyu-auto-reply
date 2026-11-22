"""订单发货结果快照：区分防重与完成状态，保留中断告警并阻止误触发续售。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.xy_order import XYOrder
from common.services.agent_delivery_settlement import (
    SETTLEMENT_RESULT_KEY,
    read_settlement_result,
)

DELIVERY_RESULT_KEY = "delivery_result"


def read_delivery_result(order_or_metadata: Any) -> dict | None:
    """从订单模型、兼容快照或元数据读取结构化结果；无有效快照时返回 None。"""
    if isinstance(order_or_metadata, dict):
        metadata = order_or_metadata.get("metadata_json", order_or_metadata)
    else:
        metadata = getattr(order_or_metadata, "metadata_json", None)
    result = metadata.get(DELIVERY_RESULT_KEY) if isinstance(metadata, dict) else None
    settlement = read_settlement_result(order_or_metadata)
    settlement_failed = bool(settlement and settlement.get("status") in {"pending", "failed"})
    if not isinstance(result, dict) and not settlement_failed:
        return None
    normalized = dict(result) if isinstance(result, dict) else {}
    # 一个缺失或非法字段不能掩盖另一个明确的中断标记；只认 JSON 布尔值。
    for key in ("delivery_incomplete", "delivery_configuration_changed", "agent_settlement_failed"):
        normalized[key] = normalized.get(key) is True
    if settlement_failed:
        normalized["agent_settlement_failed"] = True
        normalized["message"] = "；".join(filter(None, (normalized.get("message"), settlement.get("message"))))
    return normalized


def has_incomplete_delivery(order_or_metadata: Any) -> bool:
    """判断是否有未完成或配置中断的发货结果；不根据中文失败文案猜测历史状态。"""
    result = read_delivery_result(order_or_metadata)
    return bool(result and (
        result["delivery_incomplete"] or result["delivery_configuration_changed"]
        or result.get("agent_settlement_failed")
    ))


def completed_delivery_condition():
    """生成与 Python 判断一致的 SQL 条件，兼容未写新快照的历史订单。"""
    result = XYOrder.metadata_json[DELIVERY_RESULT_KEY]
    conditions = []
    for key in ("delivery_incomplete", "delivery_configuration_changed", "agent_settlement_failed"):
        flag = result[key]
        # MySQL 的布尔转换会接受数字 1；类型校验与 Python 的 is True 保持一致。
        is_interrupted = and_(func.json_type(flag) == "BOOLEAN", flag.as_boolean().is_(True))
        conditions.append(func.coalesce(is_interrupted, False).is_(False))
    settlement_status = XYOrder.metadata_json[SETTLEMENT_RESULT_KEY]["status"].as_string()
    conditions.append(func.coalesce(settlement_status.in_(["pending", "failed"]), False).is_(False))
    return and_(*conditions)


def merge_delivery_result(metadata: Any, result: dict) -> dict:
    """合并当前结果并保留其他元数据；卡密仍由原发货内容字段保存，不重复存入快照。"""
    if not isinstance(result, dict) or not all(isinstance(result.get(key), bool) for key in (
        "delivery_incomplete", "delivery_configuration_changed",
    )):
        raise ValueError("发货结果缺少有效的完成状态")
    merged = dict(metadata) if isinstance(metadata, dict) else {}
    merged[DELIVERY_RESULT_KEY] = {
        key: value for key, value in result.items()
        if key not in {"content", "delivery_content", "image_url", "image_urls"}
    }
    return merged


async def attach_delivery_result(
    session: AsyncSession, order_no: str, values: dict, result: dict | None,
) -> dict:
    """在状态提交前锁读并合并结果；None 保留历史行为，提交和回滚由订单服务负责。"""
    if result is None:
        return values
    # 标记与状态必须在同一事务提交，不能先暴露防重标记再补中断结果。
    row = (await session.execute(select(XYOrder.metadata_json).where(
        XYOrder.order_no == order_no,
    ).with_for_update())).first()
    if row is None:
        raise ValueError("订单不存在，无法保存发货结果")
    return {**values, "metadata_json": merge_delivery_result(row[0], result)}
