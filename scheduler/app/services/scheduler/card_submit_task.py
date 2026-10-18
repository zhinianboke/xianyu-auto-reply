"""Card submission scheduled task."""
from __future__ import annotations
import asyncio
from datetime import timedelta
from typing import Any
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.http_client import get_http_client
from common.db.session import async_session_maker
from common.models.card_submit_log import XYCardSubmitLog
from common.models.user_setting import UserSetting
from common.models.xy_order import XYOrder
from common.services.card_submit_utils import MAX_CODES_PER_REQUEST, extract_card_codes, serialize_response_body
from common.utils.time_utils import get_beijing_now_naive

SUBMIT_URL_KEY = "card_push.submit_url"

class CardSubmitTask:
    """Submit cards for shipped orders with auto-submit enabled."""
    def __init__(self) -> None:
        self._execute_lock = asyncio.Lock()

    async def execute(self) -> None:
        if self._execute_lock.locked():
            logger.warning("[card_submit] previous run still active")
            return
        async with self._execute_lock:
            async with async_session_maker() as session:
                try:
                    for order in await self._load_orders(session):
                        await self._submit_order(session, order)
                except Exception as exc:
                    await session.rollback()
                    logger.error(f"[card_submit] task failed: {type(exc).__name__}: {exc}", exc_info=True)

    async def _load_orders(self, session: AsyncSession) -> list[XYOrder]:
        now = get_beijing_now_naive()
        # 时间窗口：包含当天的最近 10 天（北京时区）
        start = (now - timedelta(days=9)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        order_time = func.coalesce(XYOrder.placed_at, XYOrder.created_at)
        result = await session.execute(select(XYOrder).where(
            order_time >= start, order_time < end,
            XYOrder.status.in_(["shipped", "completed"]),
            XYOrder.auto_submit_card.is_(True), XYOrder.card_submitted.is_not(True),
            XYOrder.delivery_content.is_not(None),
            XYOrder.invite_code.is_not(None), func.trim(XYOrder.invite_code) != "",
        ).order_by(order_time.asc(), XYOrder.id.asc()).limit(100))
        return list(result.scalars().all())

    async def _submit_order(self, session: AsyncSession, order: XYOrder) -> None:
        codes = extract_card_codes(order.delivery_content)
        if not codes:
            await self._record_log(session, order, {"ok": False, "error": "no valid cards"}, False, "no valid cards")
            await session.commit(); return
        if len(codes) > MAX_CODES_PER_REQUEST:
            body = {"ok": False, "error": "too many cards", "total": len(codes)}
            await self._record_log(session, order, body, False, "too many cards")
            await session.commit(); return
        result = await session.execute(select(UserSetting.value).where(UserSetting.user_id == order.owner_id, UserSetting.key == SUBMIT_URL_KEY))
        submit_url = str(result.scalar_one_or_none() or "").strip()
        if not submit_url:
            await self._record_log(session, order, {"ok": False, "error": "submit URL not configured"}, False, "submit URL not configured")
            await session.commit(); return
        try:
            invite_code = (order.invite_code or "").strip()
            request_payload = {"codes": codes, "invite": invite_code}
            response: Any = await get_http_client().post(submit_url, headers={"Content-Type": "application/json"}, json=request_payload, timeout=30, max_retries=1)
            body = response if isinstance(response, dict) else {"response": response}
        except Exception as exc:
            body = {"ok": False, "error": f"request failed: {type(exc).__name__}: {exc}"}
        success = body.get("ok") is True
        message = "submitted" if success else str(body.get("error") or "ok is not true")
        await self._record_log(session, order, body, success, message, {"codes": codes, "invite": invite_code})
        if success:
            order.card_submitted = True
            order.card_submit_notified = False
        await session.commit()

    async def _record_log(self, session: AsyncSession, order: XYOrder, response: dict[str, Any], success: bool, result_message: str, request_body: dict[str, Any] | None = None) -> None:
        session.add(XYCardSubmitLog(owner_id=order.owner_id, order_no=order.order_no, response_body=serialize_response_body({"request": request_body or {}, "response": response}), success=success, result_message=result_message))
        await session.flush()

card_submit_task_service = CardSubmitTask()

