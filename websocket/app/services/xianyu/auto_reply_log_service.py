"""
自动回复消息日志服务

功能：
1. 写入自动回复消息日志
2. 自动补充账号、所属用户和商品标题等上下文信息
3. 统一处理消息时间和日志快照字段
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.retry import with_db_retry
from common.db.session import async_session_maker
from common.models.auto_reply_message_log import XYAutoReplyMessageLog
from common.models.user import User
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem


class AutoReplyLogService:
    """自动回复消息日志服务"""

    def __init__(self, cookie_id: str):
        """初始化日志服务"""
        self.cookie_id = cookie_id

    async def record_message(self, payload: dict[str, Any]) -> int | None:
        """写入自动回复消息日志（外层错误兜底，避免影响主流程）

        实际写库逻辑在 ``_persist_message_record`` 中执行，并由 ``@with_db_retry``
        装饰器处理"连接断开类"错误的自动重试（如 ``Lost connection``、``WinError 64`` 等）。
        重试 3 次后仍失败则抛出，由本方法捕获并记录错误日志，避免日志写入失败导致主流程中断。

        Returns:
            写入成功返回日志主键ID（供异步回写发送状态使用），失败返回 None
        """
        try:
            return await self._persist_message_record(payload)
        except Exception as e:
            logger.error(f"【{self.cookie_id}】写入自动回复消息日志失败（已重试）: {e}")
            return None

    @with_db_retry(max_retries=3, initial_delay=1.0)
    async def _persist_message_record(self, payload: dict[str, Any]) -> int | None:
        """实际写入消息日志（带数据库连接断开自动重试）

        @with_db_retry 仅对连接断开类错误重试，业务错误（如 IntegrityError）会立即抛出。

        Returns:
            写入记录的主键ID
        """
        async with async_session_maker() as session:
            account_context = await self._load_account_context(session, payload.get("item_id"))
            record = XYAutoReplyMessageLog(
                owner_id=account_context.get("owner_id"),
                owner_username=account_context.get("owner_username"),
                account_pk=account_context.get("account_pk"),
                account_id=self.cookie_id,
                account_name=account_context.get("account_name"),
                chat_id=str(payload.get("chat_id") or ""),
                item_id=self._normalize_optional_str(payload.get("item_id")),
                item_title=account_context.get("item_title"),
                order_no=self._normalize_optional_str(payload.get("order_no")),
                source_message_id=self._normalize_optional_str(payload.get("source_message_id")),
                sender_user_id=str(payload.get("sender_user_id") or "unknown"),
                sender_user_name=self._normalize_optional_str(payload.get("sender_user_name")),
                source_message=self._normalize_optional_str(payload.get("source_message")),
                source_message_time=self._parse_message_time(payload.get("msg_time")),
                process_status=str(payload.get("process_status") or "processing"),
                decision_reason=str(payload.get("decision_reason") or "processing"),
                reply_strategy=str(payload.get("reply_strategy") or "none"),
                reply_mode=str(payload.get("reply_mode") or "none"),
                matched_keyword=self._normalize_optional_str(payload.get("matched_keyword")),
                matched_rule_type=self._normalize_optional_str(payload.get("matched_rule_type")),
                default_reply_scope=self._normalize_optional_str(payload.get("default_reply_scope")),
                default_reply_once=bool(payload.get("default_reply_once", False)),
                ai_model_name=self._normalize_optional_str(payload.get("ai_model_name")),
                ai_provider_name=self._normalize_optional_str(payload.get("ai_provider_name")),
                reply_text=self._normalize_optional_str(payload.get("reply_text")),
                reply_image_url=self._normalize_optional_str(payload.get("reply_image_url")),
                reply_segments=self._normalize_json_value(payload.get("reply_segments")),
                error_message=self._normalize_optional_str(payload.get("error_message")),
                send_status=str(payload.get("send_status") or "unknown"),
                send_fail_reason=self._normalize_optional_str(payload.get("send_fail_reason")),
                raw_message_json=self._normalize_json_value(payload.get("raw_message_json")),
                context_snapshot=self._normalize_json_value(payload.get("context_snapshot")),
                send_result_json=self._normalize_json_value(payload.get("send_result_json")),
            )
            session.add(record)
            await session.commit()
            return record.id

    @with_db_retry(max_retries=3, initial_delay=1.0)
    async def update_send_status(
        self, log_id: int, send_status: str, send_fail_reason: str | None = None
    ) -> None:
        """按日志主键回写发送状态（供异步检测发送结果后调用）

        Args:
            log_id: 日志记录主键ID
            send_status: 发送状态 success / failed / unknown
            send_fail_reason: 发送失败原因（success 时传 None）
        """
        async with async_session_maker() as session:
            await session.execute(
                update(XYAutoReplyMessageLog)
                .where(XYAutoReplyMessageLog.id == log_id)
                .values(
                    send_status=send_status,
                    send_fail_reason=self._normalize_optional_str(send_fail_reason),
                )
            )
            await session.commit()

    async def safe_update_send_status(
        self, log_id: int, send_status: str, send_fail_reason: str | None = None
    ) -> None:
        """update_send_status 的错误兜底封装，避免回写失败影响主流程"""
        try:
            await self.update_send_status(log_id, send_status, send_fail_reason)
        except Exception as e:
            logger.error(f"【{self.cookie_id}】回写发送状态失败 log_id={log_id}: {e}")

    async def _load_account_context(self, session: AsyncSession, item_id: Any) -> dict[str, Any]:
        """加载账号、所属用户和商品标题信息"""
        account_stmt = select(XYAccount).where(XYAccount.account_id == self.cookie_id)
        account_result = await session.execute(account_stmt)
        account = account_result.scalars().first()
        if not account:
            return {
                "owner_id": None,
                "owner_username": None,
                "account_pk": None,
                "account_name": None,
                "item_title": None,
            }

        owner_username = await self._load_owner_username(session, account.owner_id)
        item_title = await self._load_item_title(session, account.id, item_id)
        return {
            "owner_id": account.owner_id,
            "owner_username": owner_username,
            "account_pk": account.id,
            "account_name": account.display_name,
            "item_title": item_title,
        }

    async def _load_owner_username(self, session: AsyncSession, owner_id: int | None) -> str | None:
        """加载所属用户名称"""
        if not owner_id:
            return None
        owner_stmt = select(User.username).where(User.id == owner_id)
        owner_result = await session.execute(owner_stmt)
        return owner_result.scalar_one_or_none()

    async def _load_item_title(self, session: AsyncSession, account_pk: int, item_id: Any) -> str | None:
        """加载商品标题"""
        normalized_item_id = self._normalize_optional_str(item_id)
        if not normalized_item_id:
            return None
        item_stmt = select(XYCatalogItem.title).where(
            XYCatalogItem.account_pk == account_pk,
            XYCatalogItem.item_id == normalized_item_id,
        )
        item_result = await session.execute(item_stmt)
        return item_result.scalar_one_or_none()

    def _parse_message_time(self, msg_time: Any) -> datetime | None:
        """解析消息时间"""
        if not msg_time:
            return None
        if isinstance(msg_time, datetime):
            return msg_time
        if isinstance(msg_time, str):
            try:
                return datetime.strptime(msg_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
        return None

    def _normalize_optional_str(self, value: Any) -> str | None:
        """将值规范化为可空字符串"""
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def _normalize_json_value(self, value: Any) -> Any:
        """规范化JSON字段值

        递归处理 dict/list，确保不可 JSON 序列化的对象（如 asyncio.Future、
        send_result_json 中携带的 send_future）被剔除/转字符串，避免写库失败。
        """
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            result = {}
            for k, v in value.items():
                # 跳过用于异步检测的 Future 引用，不入库
                if k == "send_future":
                    continue
                result[str(k)] = self._normalize_json_value(v)
            return result
        if isinstance(value, list):
            return [self._normalize_json_value(item) for item in value]
        return str(value)
