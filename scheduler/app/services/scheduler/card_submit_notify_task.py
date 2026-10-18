"""
卡密提交后通知买家定时任务。

功能：
1. 查询最近10天（包含当天）已提交卡密但尚未通知买家的已发货订单
2. 从卡密提交日志读取 cards 结果并拼接通知文案
3. 调用 WebSocket 服务主动发送消息，并写入统一消息日志
"""
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
from common.models.card_submit_log import XYCardSubmitLog
from common.models.user import User
from common.models.xy_account import XYAccount
from common.models.xy_order import XYOrder
from common.services.card_submit_utils import build_card_submit_notification
from common.utils.time_utils import get_beijing_now_naive


class CardSubmitNotifyTask:
    """卡密提交后通知买家任务。"""

    def __init__(self) -> None:
        self._execute_lock = asyncio.Lock()

    async def execute(self) -> None:
        """执行一轮通知，任务重入时直接跳过，避免同一订单重复发送。"""
        if self._execute_lock.locked():
            logger.warning("[卡密提交后通知买家] 上一轮尚未结束，本轮跳过")
            return
        async with self._execute_lock:
            logger.info("[卡密提交后通知买家] 任务开始执行，准备查询待通知订单")
            try:
                async with async_session_maker() as session:
                    orders = await self._load_orders(session)
                    logger.info(
                        f"[卡密提交后通知买家] 查询完成，符合条件的待通知订单数: {len(orders)}"
                    )
                    for order in orders:
                        logger.info(
                            f"[卡密提交后通知买家] 开始处理订单: order_no={order.order_no}, "
                            f"account_id={order.account_id}, buyer_id={order.buyer_id}"
                        )
                        await self._notify_order(session, order)
                    logger.info(
                        f"[卡密提交后通知买家] 本轮任务处理完成，共处理 {len(orders)} 条订单"
                    )
            except Exception as exc:
                logger.error(
                    f"[卡密提交后通知买家] 任务执行失败: {type(exc).__name__}: {exc}",
                    exc_info=True,
                )

    async def _load_orders(self, session: AsyncSession) -> list[XYOrder]:
        """查询最近10天（包含当天）符合通知条件的已发货订单。"""
        now = get_beijing_now_naive()
        # 时间窗口：包含当天的最近 10 天（北京时区）
        window_start = (now - timedelta(days=9)).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        order_time = func.coalesce(XYOrder.placed_at, XYOrder.created_at)
        result = await session.execute(
            select(XYOrder)
            .where(
                order_time >= window_start,
                order_time < tomorrow_start,
                XYOrder.status.in_(["shipped", "completed"]),
                XYOrder.card_submitted.is_(True),
                XYOrder.card_submit_notified.is_not(True),
            )
            .order_by(order_time.asc(), XYOrder.id.asc())
            .limit(100)
        )
        return list(result.scalars().all())

    async def _notify_order(self, session: AsyncSession, order: XYOrder) -> None:
        """读取最新成功提交日志并通知一笔订单的买家。"""
        log_result = await session.execute(
            select(XYCardSubmitLog)
            .where(
                XYCardSubmitLog.owner_id == order.owner_id,
                XYCardSubmitLog.order_no == order.order_no,
                XYCardSubmitLog.success.is_(True),
            )
            .order_by(XYCardSubmitLog.id.desc())
            .limit(1)
        )
        submit_log = log_result.scalars().first()
        if not submit_log:
            logger.warning(f"[卡密提交后通知买家] 订单 {order.order_no} 找不到成功提交日志")
            return

        message = build_card_submit_notification(order.order_no, submit_log.response_body)
        if not message:
            logger.warning(f"[卡密提交后通知买家] 订单 {order.order_no} 提交返回值没有有效 cards 数据")
            return

        error_message = self._validate_order_context(order)
        if error_message:
            await self._record_message_log(
                session, order, message, "failed", error_message, {"error": error_message}
            )
            await session.commit()
            return

        chat_id = order.chat_id or await self._create_chat(order)
        if not chat_id:
            error_message = "创建或获取买家会话失败"
            await self._record_message_log(
                session, order, message, "failed", error_message, {"error": error_message}
            )
            await session.commit()
            return
        if not order.chat_id:
            order.chat_id = chat_id

        response: dict[str, Any]
        logger.info(
            f"[卡密提交后通知买家] 开始调用消息发送接口: order_no={order.order_no}, "
            f"account_id={order.account_id}, chat_id={chat_id}, buyer_id={order.buyer_id}, "
            f"message_length={len(message)}"
        )
        try:
            base_url = get_settings().websocket_service_url.rstrip("/")
            response = await get_http_client().post(
                f"{base_url}/internal/accounts/{order.account_id}/send-message",
                json={
                    "chat_id": chat_id,
                    "message": message,
                    "to_user_id": str(order.buyer_id),
                    "wait_result": True,
                },
                timeout=30,
                max_retries=1,
            )
        except Exception as exc:
            response = {"success": False, "message": f"发送消息异常: {type(exc).__name__}: {exc}"}

        response_data = response.get("data") if isinstance(response.get("data"), dict) else {}
        send_status = str(response_data.get("send_status") or "failed")
        send_fail_reason = str(
            response_data.get("send_fail_reason")
            or response.get("message")
            or "消息发送失败"
        )
        sent = bool(response.get("success")) and send_status == "success"
        logger.info(
            f"[卡密提交后通知买家] 消息发送接口返回: order_no={order.order_no}, "
            f"success={response.get('success')}, send_status={send_status}, sent={sent}"
        )
        await self._record_message_log(
            session,
            order,
            message,
            "success" if sent else send_status,
            None if sent else send_fail_reason,
            response,
            chat_id=chat_id,
        )
        if sent:
            order.card_submit_notified = True
            logger.info(f"[卡密提交后通知买家] 订单 {order.order_no} 通知发送成功")
        else:
            logger.warning(
                f"[卡密提交后通知买家] 订单 {order.order_no} 通知发送失败: {send_fail_reason}"
            )
        await session.commit()

    @staticmethod
    def _validate_order_context(order: XYOrder) -> str | None:
        """校验发送主动消息所需的订单字段。"""
        missing = []
        if not order.account_id:
            missing.append("账号ID")
        if not order.buyer_id:
            missing.append("买家ID")
        if not order.item_id and not order.chat_id:
            missing.append("商品ID或会话ID")
        return f"订单缺少{'、'.join(missing)}" if missing else None

    async def _create_chat(self, order: XYOrder) -> str | None:
        """通过现有 WebSocket 内部接口创建或获取买家会话。"""
        try:
            base_url = get_settings().websocket_service_url.rstrip("/")
            response = await get_http_client().post(
                f"{base_url}/internal/accounts/{order.account_id}/create-chat",
                json={"buyer_id": str(order.buyer_id), "item_id": str(order.item_id)},
                timeout=90,
                max_retries=1,
            )
            if not response.get("success"):
                logger.warning(
                    f"[卡密提交后通知买家] 订单 {order.order_no} 创建会话失败: {response}"
                )
                return None
            return str((response.get("data") or {}).get("chat_id") or "") or None
        except Exception as exc:
            logger.error(
                f"[卡密提交后通知买家] 订单 {order.order_no} 创建会话异常: "
                f"{type(exc).__name__}: {exc}",
                exc_info=True,
            )
            return None

    async def _record_message_log(
        self,
        session: AsyncSession,
        order: XYOrder,
        message: str,
        send_status: str,
        send_fail_reason: str | None,
        send_result: dict[str, Any],
        *,
        chat_id: str | None = None,
    ) -> None:
        """把主动通知尝试写入现有消息日志表。"""
        account_result = await session.execute(
            select(XYAccount, User.username)
            .outerjoin(User, User.id == XYAccount.owner_id)
            .where(XYAccount.account_id == order.account_id)
            .limit(1)
        )
        row = account_result.first()
        account = row[0] if row else None
        owner_username = row[1] if row else None
        session.add(
            XYAutoReplyMessageLog(
                owner_id=order.owner_id,
                owner_username=owner_username,
                account_pk=account.id if account else None,
                account_id=str(order.account_id or ""),
                account_name=account.display_name if account else None,
                chat_id=str(chat_id or order.chat_id or ""),
                item_id=order.item_id,
                order_no=order.order_no,
                sender_user_id=str(order.buyer_id or "unknown"),
                sender_user_name=order.buyer_fish_nick or order.buyer_nick,
                process_status="success" if send_status == "success" else "failed",
                decision_reason="card_submit_notify",
                reply_strategy="card_submit_notify",
                reply_mode="text",
                reply_text=message,
                error_message=send_fail_reason,
                send_status=send_status,
                send_fail_reason=send_fail_reason,
                send_result_json=send_result,
                context_snapshot={"card_submit_log": True},
            )
        )


card_submit_notify_task_service = CardSubmitNotifyTask()
