"""自动续售规则与事件的接口序列化。"""
from __future__ import annotations

from typing import Any

from common.models.auto_relist_event import AutoRelistEvent
from common.models.auto_relist_rule import AutoRelistRule
from common.utils.time_utils import safe_isoformat


AUTO_RELIST_STATUS_TEXT = {
    "active": "监听中", "disabled": "已关闭", "waiting": "等待成交", "retrying": "等待重试",
    "error": "需要处理", "paused": "已暂停", "pending": "等待执行", "claimed": "已领取",
    "checking": "确认商品状态", "publishing": "发布中", "retry": "稍后重试", "success": "续售成功",
    "failed": "执行失败", "unknown": "结果未知，待对账", "migration_retry": "关联迁移重试", "skipped": "已跳过",
    "running": "执行中", "reconciling": "对账中", "manual_review": "需要人工对账",
}


def serialize_auto_relist_rule(
    rule: AutoRelistRule | None,
    *,
    can_configure: bool = True,
    latest_event: AutoRelistEvent | None = None,
) -> dict[str, Any] | None:
    """序列化规则，不返回任何 worker 领取令牌。"""
    if not rule:
        return None
    return {
        "id": rule.id,
        "material_id": rule.material_id,
        "owner_id": rule.user_id,
        "account_id": rule.account_id,
        "current_item_id": rule.current_item_id,
        "card_id": rule.card_id,
        "enabled": bool(rule.enabled),
        "delay_seconds": rule.delay_seconds,
        "status": rule.status,
        "status_text": AUTO_RELIST_STATUS_TEXT.get(rule.status, rule.status),
        "version": rule.version,
        "retry_count": rule.retry_count,
        "next_retry_at": safe_isoformat(rule.next_retry_at),
        "last_order_no": rule.last_order_no,
        "last_order_id": rule.last_order_id,
        "last_order_updated_at": safe_isoformat(rule.last_order_updated_at),
        "last_old_item_id": rule.last_old_item_id,
        "last_new_item_id": rule.last_new_item_id,
        "last_error": rule.last_error,
        "paused_reason": rule.paused_reason,
        "last_relisted_at": safe_isoformat(rule.last_relisted_at),
        "created_at": safe_isoformat(rule.created_at),
        "updated_at": safe_isoformat(rule.updated_at),
        "can_configure": can_configure,
        "publish_state": latest_event.publish_state if latest_event else "not_started",
        "result_unknown": bool(latest_event.result_unknown) if latest_event else False,
    }


def serialize_auto_relist_event(row: AutoRelistEvent) -> dict[str, Any]:
    """序列化事件，隐藏 claim_token。"""
    return {
        "id": row.id,
        "order_no": row.order_no,
        "old_item_id": row.old_item_id,
        "new_item_id": row.new_item_id or row.publish_item_id,
        "status": row.status,
        "status_text": AUTO_RELIST_STATUS_TEXT.get(row.status, row.status),
        "publish_state": row.publish_state,
        "result_unknown": bool(row.result_unknown),
        "reconcile_message": row.error_message if row.result_unknown else None,
        "attempt_count": row.attempt_count,
        "error_message": row.error_message,
        "next_retry_at": safe_isoformat(row.next_retry_at),
        "created_at": safe_isoformat(row.created_at),
        "updated_at": safe_isoformat(row.updated_at),
    }


__all__ = [
    "AUTO_RELIST_STATUS_TEXT",
    "serialize_auto_relist_rule",
    "serialize_auto_relist_event",
]
