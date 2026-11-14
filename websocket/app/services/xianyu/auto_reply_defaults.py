"""默认回复配置与匹配。由自动回复入口组合，保持现有调用签名。"""
from __future__ import annotations

from typing import Any, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.redis_client import distributed_lock
from common.models.default_reply import DefaultReply, DefaultReplyRecord


class AutoReplyDefaultsMixin:
    """封装自动回复defaults相关处理。"""

    async def get_default_reply(
        self,
        session: AsyncSession,
        send_user_name: str,
        send_user_id: str,
        send_message: str,
        chat_id: str,
        item_id: Optional[str] = None,
        msg_time: str = "",
    ) -> Optional[Any]:
        """获取默认回复
        
        支持:
        - 只回复一次功能
        - 变量替换
        - 图片回复(先发图片再发文本)
        
        Args:
            session: 数据库会话
            send_user_name: 发送者用户名
            send_user_id: 发送者用户ID
            send_message: 发送的消息内容
            chat_id: 会话ID
            item_id: 商品ID(可选)
            msg_time: 消息时间
            
        Returns:
            回复内容,None表示不回复,"EMPTY_REPLY"表示回复为空
        """
        reply_trace = self._reply_trace_var.get()
        try:
            settings = await self._get_default_reply_settings(session, self.cookie_id, item_id)
            
            if not settings or not settings.get("enabled", False):
                logger.info(f"账号 {self.cookie_id} 未启用默认回复")
                return None

            settings_item_id = settings.get("item_id")
            default_scope = "item" if settings_item_id else "account"
            if reply_trace is not None:
                reply_trace["reply_strategy"] = "default"
                reply_trace["matched_rule_type"] = f"default_{default_scope}"
                reply_trace["default_reply_scope"] = default_scope
                reply_trace["default_reply_once"] = bool(settings.get("reply_once", False))
                reply_trace.setdefault("context_snapshot", {})["default_reply_setting_item_id"] = settings_item_id

            if settings.get("reply_once", False) and chat_id:
                has_replied = await self._check_user_replied(session, self.cookie_id, chat_id, settings_item_id)
                if has_replied:
                    logger.info(f"【{self.cookie_id}】chat_id {chat_id} 已使用过默认回复,跳过(只回复一次)")
                    if reply_trace is not None:
                        reply_trace["process_status"] = "skipped"
                        reply_trace["decision_reason"] = "default_reply_once"
                    return None

            reply_type = settings.get("reply_type", "text") or "text"
            reply_content = settings.get("reply_content", "")
            reply_image = settings.get("reply_image", "")

            if reply_type == "external_contact":
                return await self._do_external_contact_default_reply(
                    session=session,
                    settings=settings,
                    settings_item_id=settings_item_id,
                    chat_id=chat_id,
                    send_user_id=send_user_id,
                    reply_trace=reply_trace,
                )

            # API 类型：调用外部接口获取回复内容，失败则不回复
            if reply_type == "api":
                api_url = settings.get("api_url", "")
                api_timeout = settings.get("api_timeout", 80)
                if not api_url or not api_url.strip():
                    logger.info(f"【{self.cookie_id}】默认回复API地址为空,不进行回复")
                    return "EMPTY_REPLY"

                # 无会话标识时不加锁，避免把不同会话的消息全局串行化
                if not chat_id:
                    return await self._do_api_default_reply(
                        session=session,
                        send_message=send_message,
                        api_url=api_url,
                        api_timeout=api_timeout,
                        settings=settings,
                        settings_item_id=settings_item_id,
                        chat_id=chat_id,
                        send_user_id=send_user_id,
                        send_user_name=send_user_name,
                        item_id=item_id,
                        msg_time=msg_time,
                        reply_trace=reply_trace,
                    )

                # 会话级串行（阻塞等待而非丢弃）：外部接口最长可等待 api_timeout 秒，
                # 期间买家在同一会话连发的多条消息若并发触发调用，会并发猛打外部接口，
                # 且 reply_once 场景下可能重复回复。故对同一 chat_id 的 API 调用串行化——
                # 后到的消息排队等前一条调用完成后再执行自己的调用，从而：
                #   1) 不漏回复：每条消息都会被依次应答（不同问题各自得到回复）；
                #   2) reply_once 正确：持锁后重新核对是否已回复，已回复才跳过；
                #   3) 不并发猛打外部接口。
                # Redis 不可用或等待超时时降级为无锁直接调用，保证可用性、绝不漏回复。
                api_lock_name = f"default_reply_api:{self.cookie_id}:{chat_id}"
                # 锁自动过期时间覆盖整个外部调用窗口，防止持锁者崩溃后死锁；
                # 但排队等待上限收敛到较小值（最多 15 秒），避免上游 DB session 与消息
                # 处理被长时间（最长 api_timeout 秒）挂起，拖垮连接池。等待超时即降级直接
                # 调用——绝大多数并发只是毫秒级排队，极少触发降级。
                lock_expire = int(api_timeout or 80) + 10
                lock_wait_timeout = min(int(api_timeout or 80), 15)
                try:
                    async with distributed_lock(
                        api_lock_name, expire=lock_expire, blocking=True, timeout=lock_wait_timeout
                    ) as api_lock:
                        if not api_lock.is_locked:
                            # 等待超时仍未拿到锁：降级直接调用，避免漏回复
                            logger.warning(
                                f"【{self.cookie_id}】chat_id {chat_id} 等待API默认回复会话锁超时，"
                                f"降级直接调用"
                            )
                            return await self._do_api_default_reply(
                                session=session,
                                send_message=send_message,
                                api_url=api_url,
                                api_timeout=api_timeout,
                                settings=settings,
                                settings_item_id=settings_item_id,
                                chat_id=chat_id,
                                send_user_id=send_user_id,
                                send_user_name=send_user_name,
                                item_id=item_id,
                                msg_time=msg_time,
                                reply_trace=reply_trace,
                            )
                        # 持锁后重新核对 reply_once：前一条同会话消息可能刚已回复并记录
                        if settings.get("reply_once", False):
                            if await self._check_user_replied(
                                session, self.cookie_id, chat_id, settings_item_id
                            ):
                                logger.info(
                                    f"【{self.cookie_id}】chat_id {chat_id} 已使用过默认回复,"
                                    f"跳过(只回复一次)"
                                )
                                if reply_trace is not None:
                                    reply_trace["process_status"] = "skipped"
                                    reply_trace["decision_reason"] = "default_reply_once"
                                return None
                        return await self._do_api_default_reply(
                            session=session,
                            send_message=send_message,
                            api_url=api_url,
                            api_timeout=api_timeout,
                            settings=settings,
                            settings_item_id=settings_item_id,
                            chat_id=chat_id,
                            send_user_id=send_user_id,
                            send_user_name=send_user_name,
                            item_id=item_id,
                            msg_time=msg_time,
                            reply_trace=reply_trace,
                        )
                except Exception as lock_exc:
                    # Redis 异常等情况降级为无锁直接调用，不阻断正常回复
                    logger.warning(
                        f"【{self.cookie_id}】API默认回复获取会话锁异常，降级无锁执行: {lock_exc}"
                    )
                    return await self._do_api_default_reply(
                        session=session,
                        send_message=send_message,
                        api_url=api_url,
                        api_timeout=api_timeout,
                        settings=settings,
                        settings_item_id=settings_item_id,
                        chat_id=chat_id,
                        send_user_id=send_user_id,
                        send_user_name=send_user_name,
                        item_id=item_id,
                        msg_time=msg_time,
                        reply_trace=reply_trace,
                    )

            if reply_image and reply_image.strip():
                logger.info(f"【{self.cookie_id}】默认回复包含图片: {reply_image}")
                pending_text_reply = None
                if reply_content and reply_content.strip():
                    try:
                        pending_text_reply = reply_content.format(
                            send_user_name=send_user_name,
                            send_user_id=send_user_id,
                            send_message=send_message,
                            item_id=item_id or "",
                        )
                    except Exception as e:
                        pending_text_reply = reply_content
                        if reply_trace is not None:
                            reply_trace.setdefault("context_snapshot", {})["default_reply_format_error"] = str(e)

                if settings.get("reply_once", False) and chat_id:
                    await self._record_user_replied(session, self.cookie_id, chat_id, settings_item_id)
                    logger.info(f"【{self.cookie_id}】记录默认回复: chat_id={chat_id}, item_id={settings_item_id}")

                if reply_trace is not None:
                    reply_trace["reply_mode"] = "text_image" if pending_text_reply else "image"
                    reply_trace["reply_image_url"] = reply_image.strip()
                    if pending_text_reply:
                        reply_trace["reply_text"] = pending_text_reply
                        reply_trace["pending_text_reply"] = pending_text_reply
                        reply_trace["reply_segments"] = [{"mode": "image", "content": reply_image.strip(), "index": 1}] + self._build_text_reply_segments(pending_text_reply)
                    else:
                        reply_trace["reply_segments"] = [{"mode": "image", "content": reply_image.strip(), "index": 1}]

                if self._is_cdn_url(reply_image.strip()):
                    return f"__IMAGE_SEND__||{reply_image.strip()}"

                dr_item_id = settings_item_id or ""
                return f"__IMAGE_SEND__|DR:{dr_item_id}|{reply_image.strip()}"

            if not reply_content or not reply_content.strip():
                logger.info(f"账号 {self.cookie_id} 默认回复内容为空,不进行回复")
                return "EMPTY_REPLY"

            try:
                formatted = reply_content.format(
                    send_user_name=send_user_name,
                    send_user_id=send_user_id,
                    send_message=send_message,
                    item_id=item_id or "",
                )

                if settings.get("reply_once", False) and chat_id:
                    await self._record_user_replied(session, self.cookie_id, chat_id, settings_item_id)
                    logger.info(f"【{self.cookie_id}】记录默认回复: chat_id={chat_id}, item_id={settings_item_id}")

                logger.info(f"【{self.cookie_id}】使用默认回复: {formatted}")
                if reply_trace is not None:
                    reply_trace["reply_mode"] = "text"
                    reply_trace["reply_text"] = formatted
                    reply_trace["reply_segments"] = self._build_text_reply_segments(formatted)
                return formatted

            except Exception as e:
                logger.error(f"默认回复变量替换失败: {e}")
                if reply_trace is not None:
                    reply_trace["reply_mode"] = "text"
                    reply_trace["reply_text"] = reply_content
                    reply_trace["reply_segments"] = self._build_text_reply_segments(reply_content)
                    reply_trace.setdefault("context_snapshot", {})["default_reply_format_error"] = str(e)
                return reply_content

        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取默认回复失败: {e}")
            return None

    async def _get_default_reply_settings(self, session: AsyncSession, account_id: str, item_id: Optional[str] = None) -> Optional[dict]:
        """获取默认回复设置
        
        优先级：商品级别 > 账号级别
        
        Args:
            session: 数据库会话
            account_id: 账号ID
            item_id: 商品ID(可选)
            
        Returns:
            默认回复设置字典
        """
        # 1. 先查商品级别的默认回复
        if item_id:
            stmt = select(DefaultReply).where(
                DefaultReply.account_id == account_id,
                DefaultReply.item_id == item_id
            )
            result = await session.execute(stmt)
            reply = result.scalars().first()
            if reply and reply.enabled:
                logger.info(f"【{account_id}】使用商品级别默认回复，item_id={item_id}")
                return {
                    "enabled": reply.enabled,
                    "reply_type": getattr(reply, "reply_type", "text") or "text",
                    "reply_content": reply.reply_content or "",
                    "reply_image": reply.reply_image or "",
                    "api_url": getattr(reply, "api_url", "") or "",
                    "api_timeout": getattr(reply, "api_timeout", 80) or 80,
                    "location_name": getattr(reply, "location_name", "") or "",
                    "location_longitude": getattr(reply, "location_longitude", "") or "",
                    "location_latitude": getattr(reply, "location_latitude", "") or "",
                    "location_title": getattr(reply, "location_title", "") or "",
                    "location_subtitle": getattr(reply, "location_subtitle", "") or "",
                    "reply_once": reply.reply_once,
                    "item_id": item_id,
                }
        
        # 2. 再查账号级别的默认回复
        stmt = select(DefaultReply).where(
            DefaultReply.account_id == account_id,
            DefaultReply.item_id.is_(None)
        )
        result = await session.execute(stmt)
        reply = result.scalars().first()
        if not reply:
            return None
        logger.info(f"【{account_id}】使用账号级别默认回复")
        return {
            "enabled": reply.enabled,
            "reply_type": getattr(reply, "reply_type", "text") or "text",
            "reply_content": reply.reply_content or "",
            "reply_image": reply.reply_image or "",
            "api_url": getattr(reply, "api_url", "") or "",
            "api_timeout": getattr(reply, "api_timeout", 80) or 80,
            "location_name": getattr(reply, "location_name", "") or "",
            "location_longitude": getattr(reply, "location_longitude", "") or "",
            "location_latitude": getattr(reply, "location_latitude", "") or "",
            "location_title": getattr(reply, "location_title", "") or "",
            "location_subtitle": getattr(reply, "location_subtitle", "") or "",
            "reply_once": reply.reply_once,
            "item_id": None,
        }

    async def _check_user_replied(self, session: AsyncSession, account_id: str, user_id: str, item_id: Optional[str] = None) -> bool:
        """检查是否已回复过该用户
        
        Args:
            session: 数据库会话
            account_id: 账号ID
            user_id: 用户ID(chat_id)
            item_id: 商品ID(可选)
        """
        if item_id:
            stmt = select(DefaultReplyRecord).where(
                DefaultReplyRecord.account_id == account_id,
                DefaultReplyRecord.item_id == item_id,
                DefaultReplyRecord.user_id == user_id,
            )
        else:
            stmt = select(DefaultReplyRecord).where(
                DefaultReplyRecord.account_id == account_id,
                DefaultReplyRecord.item_id.is_(None),
                DefaultReplyRecord.user_id == user_id,
            )
        result = await session.execute(stmt)
        return result.scalars().first() is not None

    async def _record_user_replied(self, session: AsyncSession, account_id: str, user_id: str, item_id: Optional[str] = None) -> None:
        """记录已回复用户
         
        Args:
            session: 数据库会话
            account_id: 账号ID
            user_id: 用户ID(chat_id)
            item_id: 商品ID(可选)
        """
        record = DefaultReplyRecord(account_id=account_id, item_id=item_id, user_id=user_id)
        session.add(record)
        await session.commit()
