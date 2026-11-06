"""AI回复与买家上下文。由自动回复入口组合，保持现有调用签名。"""
from __future__ import annotations

import traceback
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.xianyu.ai_reply_engine import get_ai_reply_engine
from app.services.xianyu.resource_manager import pause_manager
from common.db.session import async_session_maker
from common.models.auto_reply_message_log import XYAutoReplyMessageLog
from common.models.xy_catalog_item import XYCatalogItem
from common.models.xy_order import XYOrder


class AutoReplyAiMixin:
    """封装自动回复ai相关处理。"""

    async def get_ai_reply(
        self,
        session: AsyncSession,
        send_user_name: str,
        send_user_id: str,
        send_message: str,
        item_id: Optional[str],
        chat_id: str,
    ) -> Optional[str]:
        """获取AI回复
        
        Args:
            session: 数据库会话
            send_user_name: 发送者用户名
            send_user_id: 发送者用户ID
            send_message: 发送的消息内容
            item_id: 商品ID(可选)
            chat_id: 会话ID
            
        Returns:
            AI回复内容,None表示不使用AI回复
        """
        reply_trace = self._reply_trace_var.get()
        try:
            
            account = await self._get_account(session)
            if not account:
                return None
            
            # 【新增】检查是否开启"已下单用户禁止AI回复"开关
            if account.ai_reply_block_ordered_users:
                # 检查该买家是否在订单表中有订单记录
                has_orders = await self._check_user_has_orders(session, send_user_id)
                if has_orders:
                    logger.info(f"【{self.cookie_id}】用户 {send_user_id} 已下单，跳过AI回复（ai_reply_block_ordered_users=True）")
                    if reply_trace is not None:
                        reply_trace.setdefault("context_snapshot", {})["ai_blocked_reason"] = "ordered_user"
                        reply_trace.setdefault("context_snapshot", {})["buyer_has_orders"] = True
                    return None  # 返回None，流程会自动进入默认回复判断
            
            ai_engine = get_ai_reply_engine()
            if not await ai_engine.is_ai_enabled(self.cookie_id, session):
                logger.info(f"【{self.cookie_id}】AI回复未启用")
                return None

            ai_settings = await ai_engine.get_ai_settings(self.cookie_id, session)
            if ai_settings.get("manual_reply_ai_pause_enabled"):
                pause_minutes = int(ai_settings.get("manual_reply_ai_pause_minutes", 10) or 10)
                remaining = pause_manager.get_remaining_ai_pause_time(
                    self.cookie_id, send_user_id, item_id or ""
                )
                if remaining:
                    logger.info(
                        f"【{self.cookie_id}】买家 {send_user_id} 商品 {item_id} 正在人工回复 AI 暂停期，"
                        f"剩余 {remaining} 秒"
                    )
                    if reply_trace is not None:
                        await self._record_manual_reply_ai_paused_log(
                            reply_trace, remaining, pause_minutes
                        )
                        # 若未命中默认回复，最终日志已由上方的 AI 暂停记录覆盖，避免再写一条“未匹配规则”。
                        reply_trace["_manual_reply_ai_pause_log_recorded"] = True
                    return None
            ai_provider_name = ai_engine._get_api_provider_name(ai_settings)
            if reply_trace is not None:
                reply_trace["ai_model_name"] = ai_settings.get("model_name")
                reply_trace["ai_provider_name"] = ai_provider_name
            
            item_info = {}
            if item_id:
                stmt = select(XYCatalogItem).where(
                    XYCatalogItem.account_pk == account.id,
                    XYCatalogItem.item_id == item_id
                )
                result = await session.execute(stmt)
                item = result.scalars().first()
                
                if item:
                    price_str = item.price or "0"
                    try:
                        price_clean = ''.join(c for c in price_str if c.isdigit() or c == '.')
                        price = float(price_clean) if price_clean else 0
                    except Exception:
                        price = 0
                    
                    metadata = item.metadata_json or {}
                    desc = metadata.get("detail", "") or metadata.get("description", "") or ""
                    item_info = {
                        "title": item.title or "未知商品",
                        "price": price,
                        "desc": desc or "暂无商品描述",
                        "ai_prompt": item.ai_prompt or "",
                    }
                else:
                    logger.warning(f"【{self.cookie_id}】未找到商品信息: item_id={item_id}")
                    item_info = {
                        "title": "商品信息获取失败",
                        "price": 0,
                        "desc": "暂无商品描述",
                        "ai_prompt": "",
                    }
            else:
                item_info = {
                    "title": "未知商品",
                    "price": 0,
                    "desc": "暂无商品描述",
                    "ai_prompt": "",
                }

            if reply_trace is not None:
                reply_trace.setdefault("context_snapshot", {})["ai_item_info"] = item_info
            
            reply = await ai_engine.generate_reply(
                message=send_message,
                item_info=item_info,
                chat_id=chat_id,
                cookie_id=self.cookie_id,
                user_id=send_user_id,
                item_id=item_id or "",
                db_session=session,
                skip_wait=True,
            )
            
            if reply:
                logger.info(f"【{self.cookie_id}】AI回复生成成功: {reply[:50]}...")
                if reply_trace is not None:
                    reply_trace["reply_strategy"] = "ai"
                    reply_trace["matched_rule_type"] = "ai"
                    reply_trace["reply_mode"] = "text"
                    reply_trace["reply_text"] = reply
                    reply_trace["reply_segments"] = self._build_text_reply_segments(reply)
                return reply

            logger.info(f"【{self.cookie_id}】AI回复生成失败或返回空")
            return None
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取AI回复失败: {e}")
            return None

    async def _pause_ai_reply_after_manual_message(
        self, chat_id: str, item_id: str, log_payload: Dict[str, Any]
    ) -> bool:
        """人工回复后，按账号、买家和商品维度暂停 AI 回复。

        暂停上下文优先取内存中最近一次买家消息；内存缺失（服务重启、卖家主动
        发起会话等）时，从自动回复日志表按会话反查最近一条真实买家消息兜底。

        Args:
            chat_id: 会话ID
            item_id: 本次人工消息携带的商品ID（可能为空）
            log_payload: 当前消息日志载体，用于写入暂停上下文快照
        Returns:
            True 表示已成功设置 AI 暂停；False 表示未开启开关或无法定位买家上下文，
            此时调用方应回退到原有的整会话暂停逻辑。
        """
        try:

            async with async_session_maker() as session:
                settings = await get_ai_reply_engine().get_ai_settings(
                    self.cookie_id, session
                )

            if not settings.get("manual_reply_ai_pause_enabled"):
                return False

            pause_minutes = int(settings.get("manual_reply_ai_pause_minutes", 10) or 10)
            # 1. 优先使用内存中最近一次买家消息上下文
            paused_context = pause_manager.pause_ai_reply_for_manual_message(
                chat_id, self.cookie_id, item_id, pause_minutes
            )
            # 2. 内存未命中时，从日志表反查最近一条买家消息兜底
            if not paused_context:
                fallback = await self._lookup_buyer_context_from_db(chat_id, item_id)
                if fallback:
                    buyer_id, fallback_item_id = fallback
                    paused_context = pause_manager.pause_ai_reply(
                        self.cookie_id, buyer_id, fallback_item_id, pause_minutes
                    )

            if not paused_context:
                logger.info(
                    f"【{self.cookie_id}】人工回复 AI 暂停未生效：会话 {chat_id} 无可用买家上下文，"
                    f"回退为整会话暂停"
                )
                return False

            buyer_id, paused_item_id = paused_context
            log_payload.setdefault("context_snapshot", {}).update({
                "manual_reply_ai_pause_minutes": pause_minutes,
                "manual_reply_ai_pause_buyer_id": buyer_id,
                "manual_reply_ai_pause_item_id": paused_item_id,
            })
            return True
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】设置人工回复 AI 暂停失败: {e}")
            return False

    async def _lookup_buyer_context_from_db(
        self, chat_id: str
    ) -> tuple[str, str]:
        """从自动回复日志表兜底反查会话最近一次的真实买家上下文。

        用于内存上下文缺失（服务重启、卖家主动发起会话等）时，
        仍能按买家+商品维度精确暂停 AI。

        Args:
            chat_id: 会话ID
        Returns:
            (buyer_id, item_id)；查不到时返回 ("", "")
        """
        normalized_chat_id = str(chat_id or "").strip()
        if not normalized_chat_id:
            return "", ""
        try:
            myid = getattr(self.xianyu_instance, "myid", self.cookie_id)
            async with async_session_maker() as session:
                # 取该账号该会话中，最近一条由买家（非卖家自己）发来的消息
                stmt = (
                    select(
                        XYAutoReplyMessageLog.sender_user_id,
                        XYAutoReplyMessageLog.item_id,
                    )
                    .where(
                        XYAutoReplyMessageLog.account_id == self.cookie_id,
                        XYAutoReplyMessageLog.chat_id == normalized_chat_id,
                        XYAutoReplyMessageLog.sender_user_id != myid,
                    )
                    .order_by(XYAutoReplyMessageLog.created_at.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                row = result.first()
            if not row:
                return "", ""
            buyer_id = str(row[0] or "").strip()
            item_id = str(row[1] or "").strip()
            return buyer_id, item_id
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】从数据库反查买家上下文失败: {e}")
            return "", ""

    async def _check_user_has_orders(self, session: AsyncSession, buyer_user_id: str) -> bool:
        """检查指定买家在当前账号下是否有订单记录
        
        Args:
            session: 数据库会话
            buyer_user_id: 买家用户ID
            
        Returns:
            True表示有订单，False表示无订单
        """
        try:
            # 防御性检查：买家ID为空时直接返回False
            if not buyer_user_id or not buyer_user_id.strip():
                logger.info(f"【{self.cookie_id}】买家ID为空，跳过订单检查")
                return False
            
            # 检查订单表中是否存在该买家的订单记录
            # 使用 account_id 字段匹配卖家账号（对应订单表的 seller_account_id）
            # 注意：account_id 和 buyer_id 都可能为 None，需要显式排除
            stmt = select(exists().where(
                XYOrder.account_id == self.cookie_id,
                XYOrder.buyer_id == buyer_user_id,
                XYOrder.account_id.isnot(None),  # 显式排除 account_id 为空的记录
                XYOrder.buyer_id.isnot(None),    # 显式排除 buyer_id 为空的记录
            ))
            result = await session.execute(stmt)
            has_orders = result.scalar()
            
            logger.info(f"【{self.cookie_id}】检查买家 {buyer_user_id} 订单记录: {has_orders}")
            return bool(has_orders)
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】检查买家订单记录失败: {e}")
            logger.error(traceback.format_exc())
            # 出错时返回False，不影响正常流程
            return False
