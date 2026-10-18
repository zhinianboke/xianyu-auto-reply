"""Card processing result scheduled task."""
from __future__ import annotations
import asyncio
from datetime import timedelta
from typing import Any
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.http_client import get_http_client
from common.db.session import async_session_maker
from common.models.auto_reply_message_log import XYAutoReplyMessageLog
from common.models.user import User
from common.models.xy_account import XYAccount
from common.models.xy_order import XYOrder
from common.models.user_setting import UserSetting
from common.models.card_process_result_log import XYCardProcessResultLog
from common.services.card_submit_utils import (
    build_card_submit_notification,
    extract_card_codes,
    serialize_response_body,
)
from common.utils.time_utils import get_beijing_now_naive
QUERY_URL_KEY = "card_push.status_query_url"
class CardProcessResultTask:
    """Query card processing results and notify buyer when all cards succeed."""
    def __init__(self) -> None:
        self._execute_lock = asyncio.Lock()
    async def execute(self) -> None:
        if self._execute_lock.locked():
            logger.warning("[card_process_result] previous run is still active")
            return
        async with self._execute_lock:
            async with async_session_maker() as session:
                try:
                    for order in await self._load_orders(session):
                        await self._process_order(session, order)
                except Exception as exc:
                    await session.rollback()
                    logger.error(f"[card_process_result] task failed: {type(exc).__name__}: {exc}", exc_info=True)
    async def _load_orders(self, session: AsyncSession) -> list[XYOrder]:
        now = get_beijing_now_naive()
        start = (now - timedelta(days=9)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        order_time = func.coalesce(XYOrder.placed_at, XYOrder.created_at)
        result = await session.execute(select(XYOrder).where(order_time >= start, order_time < end, XYOrder.status.in_(["shipped", "completed"]), XYOrder.card_submitted.is_(True), (XYOrder.card_process_result.is_(None) | (XYOrder.card_process_result != "success")), XYOrder.delivery_content.is_not(None)).order_by(order_time.asc(), XYOrder.id.asc()).limit(100))
        return list(result.scalars().all())
    async def _process_order(self, session: AsyncSession, order: XYOrder) -> None:
        codes = extract_card_codes(order.delivery_content)
        if not codes:
            logger.warning(f"[card_process_result] order {order.order_no} has no cards")
            return
        result = await session.execute(select(UserSetting.value).where(UserSetting.user_id == order.owner_id, UserSetting.key == QUERY_URL_KEY))
        query_url = str(result.scalar_one_or_none() or "").strip()
        if not query_url:
            logger.warning(f"[card_process_result] order {order.order_no} query URL is not configured")
            return
        try:
            response: Any = await get_http_client().post(query_url, headers={"Content-Type": "application/json"}, json={"codes": codes}, timeout=30, max_retries=1)
        except Exception as exc:
            session.add(XYCardProcessResultLog(owner_id=order.owner_id, order_no=order.order_no, request_body=serialize_response_body({"codes": codes}), response_body="", trigger_scene="scheduled", success=False, result_message=str(exc)))
            await session.commit()
            logger.error(f"[card_process_result] order {order.order_no} query failed: {type(exc).__name__}: {exc}", exc_info=True)
            return
        body = response if isinstance(response, dict) else {"response": response}
        cards = body.get("cards") if isinstance(body.get("cards"), list) else []
        if not cards:
            session.add(XYCardProcessResultLog(owner_id=order.owner_id, order_no=order.order_no, request_body=serialize_response_body({"codes": codes}), response_body=serialize_response_body(body), trigger_scene="scheduled", success=False, result_message="接口未返回cards"))
            await session.commit()
            logger.warning(f"[card_process_result] order {order.order_no} returned no cards: {serialize_response_body(body)}")
            return
        all_success = len(cards) >= len(codes) and all(isinstance(card, dict) and str(card.get("group") or "").lower() == "success" for card in cards)
        if not all_success:
            # 浠嶅湪澶勭悊涓紱淇濈暀鏈垚鍔熺姸鎬侊紝涓嬩竴杞户缁煡璇€?            
            order.card_process_result = "processing"
            session.add(XYCardProcessResultLog(owner_id=order.owner_id, order_no=order.order_no, request_body=serialize_response_body({"codes": codes}), response_body=serialize_response_body(body), trigger_scene="scheduled", success=True, result_message="查询完成，仍在处理中"))
            await session.commit()
            return
        sent = await self._notify_buyer(session, order, cards)
        if sent:
            order.card_process_result = "success"
        session.add(XYCardProcessResultLog(owner_id=order.owner_id, order_no=order.order_no, request_body=serialize_response_body({"codes": codes}), response_body=serialize_response_body(body), trigger_scene="scheduled", success=True, result_message="全部卡密处理成功" if sent else "全部成功但通知买家失败"))
        await session.commit()
    async def _notify_buyer(self, session: AsyncSession, order: XYOrder, cards: list[dict[str, Any]]) -> bool:
        message = build_card_submit_notification(order.order_no, {"cards": cards})
        if not message:
            logger.warning(f"[card_process_result] order {order.order_no} has no valid card result message")
            return False
        if not order.account_id or not order.buyer_id or (not order.item_id and not order.chat_id):
            await self._record_message_log(session, order, message, "failed", "璁㈠崟缂哄皯涔板浼氳瘽淇℃伅", {})
            return False
        chat_id = order.chat_id
        try:
            base = get_settings().websocket_service_url.rstrip("/")
            if not chat_id:
                created = await get_http_client().post(f"{base}/internal/accounts/{order.account_id}/create-chat", json={"buyer_id": str(order.buyer_id), "item_id": str(order.item_id)}, timeout=90, max_retries=1)
                chat_id = str((created.get("data") or {}).get("chat_id") or "") or None
            if not chat_id:
                raise RuntimeError("buyer chat unavailable")
            response = await get_http_client().post(f"{base}/internal/accounts/{order.account_id}/send-message", json={"chat_id": chat_id, "message": message, "to_user_id": str(order.buyer_id), "wait_result": True}, timeout=30, max_retries=1)
        except Exception as exc:
            await self._record_message_log(session, order, message, "failed", str(exc), {})
            return False
        data = response.get("data") if isinstance(response, dict) and isinstance(response.get("data"), dict) else {}
        sent = bool(response.get("success")) and str(data.get("send_status") or "failed") == "success"
        await self._record_message_log(session, order, message, "success" if sent else "failed", None if sent else str(response.get("message") or "send failed"), response, chat_id)
        if sent:
            order.chat_id = chat_id
            order.card_submit_notified = True
        return sent
    async def _record_message_log(self, session: AsyncSession, order: XYOrder, message: str, status: str, reason: str | None, result: dict[str, Any], chat_id: str | None = None) -> None:
        row = (await session.execute(select(XYAccount, User.username).outerjoin(User, User.id == XYAccount.owner_id).where(XYAccount.account_id == order.account_id).limit(1))).first()
        account, username = (row[0], row[1]) if row else (None, None)
        session.add(XYAutoReplyMessageLog(owner_id=order.owner_id, owner_username=username, account_pk=account.id if account else None, account_id=str(order.account_id or ""), account_name=account.display_name if account else None, chat_id=str(chat_id or order.chat_id or ""), item_id=order.item_id, order_no=order.order_no, sender_user_id=str(order.buyer_id or "unknown"), sender_user_name=order.buyer_fish_nick or order.buyer_nick, process_status="success" if status == "success" else "failed", decision_reason="card_process_result", reply_strategy="card_process_result", reply_mode="text", reply_text=message, error_message=reason, send_status=status, send_fail_reason=reason, send_result_json=result, context_snapshot={"card_process_result": True}))
card_process_result_task_service = CardProcessResultTask()

