"""
公开消息日志查询服务。

功能：
1. 使用分销秘钥校验调用方身份并限定用户数据范围。
2. 按商品 ID 查询该用户的消息日志。
3. 复用内部消息日志服务完成消息类型筛选和分页查询。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_reply_log_service import AutoReplyLogService
from app.services.external_account_service import ExternalAccountService
from common.models.user import UserStatus


class ExternalMessageLogAccessError(RuntimeError):
    """公开消息日志接口身份校验失败。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _serialize_public_log(log: dict[str, Any]) -> dict[str, Any]:
    """
    移除消息日志中的内部用户字段，保留公开查询所需的信息。

    Args:
        log: AutoReplyLogService 序列化后的消息日志。
    Returns:
        可供外部调用方使用的消息日志。
    """
    return {
        "id": log.get("id"),
        "account_id": log.get("account_id"),
        "account_name": log.get("account_name"),
        "chat_id": log.get("chat_id"),
        "item_id": log.get("item_id"),
        "item_title": log.get("item_title"),
        "order_no": log.get("order_no"),
        "source_message_id": log.get("source_message_id"),
        "sender_user_id": log.get("sender_user_id"),
        "sender_user_name": log.get("sender_user_name"),
        "source_message": log.get("source_message"),
        "source_message_time": log.get("source_message_time"),
        "process_status": log.get("process_status"),
        "decision_reason": log.get("decision_reason"),
        "reply_strategy": log.get("reply_strategy"),
        "reply_mode": log.get("reply_mode"),
        "matched_keyword": log.get("matched_keyword"),
        "matched_rule_type": log.get("matched_rule_type"),
        "default_reply_scope": log.get("default_reply_scope"),
        "default_reply_once": bool(log.get("default_reply_once")),
        "ai_model_name": log.get("ai_model_name"),
        "ai_provider_name": log.get("ai_provider_name"),
        "reply_text": log.get("reply_text"),
        "reply_image_url": log.get("reply_image_url"),
        "error_message": log.get("error_message"),
        "send_status": log.get("send_status"),
        "send_fail_reason": log.get("send_fail_reason"),
        "created_at": log.get("created_at"),
        "updated_at": log.get("updated_at"),
    }


class ExternalMessageLogQueryService:
    """按公开接口身份查询商品消息日志。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _resolve_owner_id(self, secret_key: str) -> int:
        """根据分销秘钥解析可访问消息日志的用户 ID。"""
        user = await ExternalAccountService(self.session).get_user_by_secret(secret_key)
        if user is None:
            raise ExternalMessageLogAccessError(40001, "秘钥不存在")
        if user.status == UserStatus.DELETED:
            raise ExternalMessageLogAccessError(40001, "秘钥对应的用户不可用")
        return user.id

    async def list_logs(
        self,
        secret_key: str,
        *,
        item_id: str,
        message_type: str = "auto_reply",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """
        查询秘钥所属用户指定商品的消息日志并返回分页结果。

        Args:
            secret_key: 分销秘钥。
            item_id: 商品 ID。
            message_type: 消息类型，支持 auto_reply 或 auto_delivery。
            page: 页码，从 1 开始。
            page_size: 每页数量。
        Returns:
            包含 list、total、page、page_size 和 total_pages 的分页数据。
        """
        owner_id = await self._resolve_owner_id(secret_key.strip())
        logs, total = await AutoReplyLogService(self.session).list_logs(
            owner_id=owner_id,
            item_id=item_id.strip(),
            message_type=message_type,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        data = [_serialize_public_log(log) for log in logs]
        return {
            "list": data,
            "logs": data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }


__all__ = [
    "ExternalMessageLogAccessError",
    "ExternalMessageLogQueryService",
]
