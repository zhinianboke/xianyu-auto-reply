"""聊天消息处理。由自动回复入口组合，保持现有调用签名。"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from loguru import logger

from app.services.xianyu.api_keyword_handler import ApiKeywordHandler
from app.services.xianyu.rate_service import check_item_belongs_to_account
from app.services.xianyu.resource_manager import pause_manager
from common.db.session import async_session_maker


class AutoReplyChatMixin:
    """封装自动回复chat相关处理。"""

    async def handle_chat_message(self, parsed_message: Dict[str, Any], websocket) -> None:
        """处理聊天消息(主入口)
        
        流程:
        1. 检查是否是自己发出的消息(手动发出则暂停自动回复)
        2. 检查是否是系统消息(跳过不需要回复的系统消息)
        3. 检查是否是自动发货触发消息(这些消息由自动发货处理，不进行自动回复)
        4. 检查商品是否属于当前账号(不属于则跳过自动回复)
        5. 检查消息等待时间(去重)
        6. 检查消息过滤(跳过自动回复)
        7. 获取自动回复内容
        8. 发送回复消息
        9. 发送消息通知(如果未被过滤)
        
        Args:
            parsed_message: 解析后的消息数据
            websocket: WebSocket连接
        """
        log_payload = self._build_auto_reply_log_payload(parsed_message)
        reply_trace_token = self._reply_trace_var.set(log_payload)
        api_handler = None
        try:
            send_user_id = parsed_message.get("send_user_id", "")
            send_user_name = parsed_message.get("send_user_name", "")
            send_message = parsed_message.get("send_message", "")
            chat_id = parsed_message.get("chat_id", "")
            item_id = parsed_message.get("item_id", "")
            msg_time = parsed_message.get("msg_time", "")
            
            # 1. 检查是否是自己发出的消息（手动发出）
            # 使用myid判断（参照旧框架）
            myid = getattr(self.xianyu_instance, 'myid', self.cookie_id)
            self._merge_log_context(log_payload, myid=myid)
            if send_user_id == myid:
                # 手动发出消息。启用 AI 专用暂停时，仅暂停同买家同商品的 AI；
                # 未启用时保留原有按会话暂停全部自动回复的行为。
                log_payload["process_status"] = "skipped"
                log_payload["decision_reason"] = "self_message"
                ai_pause_enabled = await self._pause_ai_reply_after_manual_message(
                    chat_id, item_id, log_payload
                )
                if not ai_pause_enabled:
                    pause_manager.pause_chat(chat_id, self.cookie_id)
                return
            
            # 2. 检查是否是系统消息（参照旧框架message_handler_core.py）
            # 这些系统消息不需要自动回复
            if self.is_system_message_to_skip(send_message):
                logger.info(f"【{self.cookie_id}】系统消息跳过自动回复: {send_message}")
                log_payload["process_status"] = "skipped"
                log_payload["decision_reason"] = "system_message"
                # 系统消息仍然需要发送通知
                skip_notify_keywords = await self.get_filter_keywords('skip_notify')
                should_skip_notification = self.should_skip_notify(send_message, skip_notify_keywords)
                if not should_skip_notification:
                    await self._send_notification(
                        send_user_name=send_user_name,
                        send_user_id=send_user_id,
                        send_message=send_message,
                        chat_id=chat_id,
                        item_id=item_id,
                        msg_time=msg_time,
                    )
                return
            
            # 3. 检查是否是自动发货触发消息（参照旧框架）
            # 这些消息应该由自动发货流程处理，不进行自动回复
            if self.is_auto_delivery_trigger(send_message):
                logger.info(f"【{self.cookie_id}】自动发货触发消息，跳过自动回复: {send_message}")
                log_payload["process_status"] = "skipped"
                log_payload["decision_reason"] = "auto_delivery_trigger"
                # 自动发货消息仍然需要发送通知
                skip_notify_keywords = await self.get_filter_keywords('skip_notify')
                should_skip_notification = self.should_skip_notify(send_message, skip_notify_keywords)
                if not should_skip_notification:
                    await self._send_notification(
                        send_user_name=send_user_name,
                        send_user_id=send_user_id,
                        send_message=send_message,
                        chat_id=chat_id,
                        item_id=item_id,
                        msg_time=msg_time,
                    )
                return
            
            # 4. 检查商品是否属于当前账号
            # 只有商品ID存在时才检查归属，商品ID不存在则继续执行原有逻辑
            if item_id:
                belongs_to_account = await check_item_belongs_to_account(self.cookie_id, item_id)
                self._merge_log_context(log_payload, belongs_to_account=belongs_to_account)
                if not belongs_to_account:
                    logger.info(f"【{self.cookie_id}】商品 {item_id} 不属于当前账号，跳过自动回复")
                    log_payload["process_status"] = "skipped"
                    log_payload["decision_reason"] = "item_not_belong"
                    # 商品不属于当前账号，仍然发送通知
                    skip_notify_keywords = await self.get_filter_keywords('skip_notify')
                    should_skip_notification = self.should_skip_notify(send_message, skip_notify_keywords)
                    if not should_skip_notification:
                        await self._send_notification(
                            send_user_name=send_user_name,
                            send_user_id=send_user_id,
                            send_message=send_message,
                            chat_id=chat_id,
                            item_id=item_id,
                            msg_time=msg_time,
                        )
                    return
            # 商品ID不存在时继续执行原有逻辑

            # 保存买家和商品上下文。人工回复消息只会携带卖家自己的 ID，
            # 需复用此前买家消息中的 buyer_id，才能按买家+商品精确暂停 AI。
            # 仅记录已排除系统消息且已通过商品归属校验的真实买家消息。
            pause_manager.remember_buyer_context(
                chat_id, self.cookie_id, send_user_id, item_id
            )
            
            # 5. 检查消息等待时间(去重，参照旧框架reply_scheduler.py)
            # 同一会话的同一消息内容在等待时间内不重复回复
            if await self._check_chat_processed(chat_id, send_message):
                logger.info(f"【{self.cookie_id}】消息 '{send_message[:30]}...' 在等待时间内已处理过，跳过自动回复")
                log_payload["process_status"] = "skipped"
                log_payload["decision_reason"] = "duplicate_message"
                return
            
            # 6. 检查消息过滤(跳过自动回复)
            skip_reply_keywords = await self.get_filter_keywords('skip_reply')
            logger.info(f"【{self.cookie_id}】消息过滤关键词: {skip_reply_keywords}")
            should_skip = self.should_skip_reply(send_message, skip_reply_keywords)
            self._merge_log_context(
                log_payload,
                skip_reply_keywords=skip_reply_keywords,
                should_skip_reply=should_skip,
            )
            logger.info(f"【{self.cookie_id}】消息过滤结果: should_skip={should_skip}, message={send_message[:30]}")
            
            # 7. 获取并发送自动回复
            send_results: List[Dict[str, Any]] = []
            if not should_skip:
                # 清除之前的待发送文本
                log_payload.pop("pending_text_reply", None)
                
                reply = await self.get_reply(
                    send_user_name=send_user_name,
                    send_user_id=send_user_id,
                    send_message=send_message,
                    chat_id=chat_id,
                    item_id=item_id,
                    msg_time=msg_time,
                )
                
                if reply:
                    # 标记该消息已处理(在发送回复前标记，参照旧框架)
                    await self._mark_chat_processed(chat_id, send_message)
                    
                    # 自动回复延迟：按账号配置在发送前等待指定秒数
                    reply_delay = await self._load_reply_delay()
                    if reply_delay > 0:
                        logger.info(f"【{self.cookie_id}】自动回复延迟 {reply_delay} 秒后发送")
                        await asyncio.sleep(reply_delay)
                    
                    # 延迟结束后再次检测是否被人工介入暂停
                    if pause_manager.is_chat_paused(chat_id, self.cookie_id):
                        logger.info(f"【{self.cookie_id}】自动回复延迟结束，但检测到会话 {chat_id} 已被人工介入暂停，放弃发送回复")
                        log_payload["process_status"] = "skipped"
                        if isinstance(reply, dict) and reply.get("_reply_mode") in ("external_contact", "api_keyword"):
                            await self._unmark_chat_processed(chat_id, send_message)
                        log_payload["decision_reason"] = "chat_paused_after_delay"
                        return
                    
                    # 检查是否是图片发送指令
                    # 格式：__IMAGE_SEND__|类型标识|image_url
                    # 类型标识：KW:keyword（关键词）、DR:item_id（默认回复）、空（不需要更新）
                    if isinstance(reply, dict) and reply.get("_reply_mode") == "api_keyword":
                        api_handler = ApiKeywordHandler(
                            self, websocket, chat_id, send_user_id, item_id,
                        )
                        send_results = await api_handler.run(reply["config"], send_message)
                        if log_payload.get("_api_keyword_error") or log_payload.get("process_status") == "skipped":
                            await self._unmark_chat_processed(chat_id, send_message)
                    elif isinstance(reply, dict) and reply.get("_reply_mode") == "external_contact":
                        try:
                            external_result = await self.xianyu_instance.send_raw_message(
                                websocket=websocket,
                                message=reply.get("message"),
                            )
                        except Exception as send_exc:  # noqa: BLE001
                            external_result = {
                                "success": False,
                                "mode": "external_contact",
                                "error_message": str(send_exc),
                            }
                        send_results.append(
                            external_result
                            or self._build_empty_send_result("external_contact", "remote_location_message")
                        )
                        if not external_result or not external_result.get("success"):
                            await self._unmark_chat_processed(chat_id, send_message)
                        if (
                            external_result
                            and external_result.get("success")
                            and reply.get("reply_once")
                            and chat_id
                        ):
                            try:
                                async with async_session_maker() as record_session:
                                    await self._record_user_replied(
                                        record_session,
                                        self.cookie_id,
                                        chat_id,
                                        reply.get("settings_item_id"),
                                    )
                                logger.info(
                                    f"【{self.cookie_id}】记录站外联系方式默认回复: "
                                    f"chat_id={chat_id}, item_id={reply.get('settings_item_id')}"
                                )
                            except Exception as record_exc:  # noqa: BLE001
                                logger.warning(
                                    f"【{self.cookie_id}】记录站外联系方式 reply_once 失败: {record_exc}"
                                )
                    elif reply.startswith("__IMAGE_SEND__"):
                        # 解析图片发送指令：去掉前缀后格式为 |类型标识|image_url
                        content = reply.replace("__IMAGE_SEND__", "")
                        # 去掉开头的 | 后分割
                        if content.startswith("|"):
                            content = content[1:]
                        parts = content.split("|", 1)
                        
                        update_type = None  # 更新类型：KW/DR/None
                        update_key = None   # 更新键：keyword或item_id
                        
                        if len(parts) >= 2:
                            type_part = parts[0]
                            image_url = parts[1]
                            
                            if type_part.startswith("KW:"):
                                # 关键词图片
                                update_type = "KW"
                                update_key = type_part[3:]  # 去掉 "KW:" 前缀
                            elif type_part.startswith("DR:"):
                                # 默认回复图片
                                update_type = "DR"
                                update_key = type_part[3:] or None  # 去掉 "DR:" 前缀，空字符串转None
                            else:
                                # 兼容旧格式（直接是keyword）
                                update_type = "KW" if type_part else None
                                update_key = type_part if type_part else None
                        else:
                            # 兼容旧格式（只有image_url）
                            image_url = parts[0] if parts else content
                        
                        # 根据类型传递不同参数
                        if update_type == "KW":
                            image_result = await self.xianyu_instance.send_image_msg(
                                websocket=websocket,
                                chat_id=chat_id,
                                send_user_id=send_user_id,
                                image_url=image_url,
                                keyword=update_key,  # 传递关键词用于更新
                            )
                        elif update_type == "DR":
                            image_result = await self.xianyu_instance.send_image_msg(
                                websocket=websocket,
                                chat_id=chat_id,
                                send_user_id=send_user_id,
                                image_url=image_url,
                                default_reply_item_id=update_key,  # 传递默认回复item_id用于更新
                            )
                        else:
                            image_result = await self.xianyu_instance.send_image_msg(
                                websocket=websocket,
                                chat_id=chat_id,
                                send_user_id=send_user_id,
                                image_url=image_url,
                            )
                        send_results.append(image_result or self._build_empty_send_result("image", image_url))
                        logger.info(f"【{self.cookie_id}】发送图片回复: {image_url}")
                        
                        # 如果有待发送的文本，继续发送（支持分隔符拆分）
                        pending_text_reply = log_payload.pop("pending_text_reply", None)
                        if pending_text_reply:
                            send_results.extend(
                                await self._send_text_with_separator(
                                    websocket=websocket,
                                    chat_id=chat_id,
                                    send_user_id=send_user_id,
                                    text=pending_text_reply,
                                )
                            )
                    else:
                        # 普通文本消息，支持分隔符拆分
                        send_results = await self._send_text_with_separator(
                            websocket=websocket,
                            chat_id=chat_id,
                            send_user_id=send_user_id,
                            text=reply,
                        )
            
            else:
                log_payload["process_status"] = "skipped"
                log_payload["decision_reason"] = "skip_reply_filter"
            
            if send_results:
                log_payload["send_result_json"] = send_results
                failed_results = [result for result in send_results if not result.get("success", False)]
                if not failed_results:
                    log_payload["process_status"] = "success"
                    log_payload["decision_reason"] = "reply_sent"
                    # API同步发货已等待拦截检测；其他未等待的消息由后台继续回写。
                    api_send_checked = log_payload.pop("_api_send_checked", False)
                    has_pending_send = any(result.get("send_future") is not None for result in send_results)
                    log_payload["send_status"] = "success" if api_send_checked and not has_pending_send else "unknown"
                    # 收集本次发出消息的 (future, mid)，供异步检测发送结果
                    log_payload["_pending_send_waiters"] = [
                        (result.get("send_future"), result.get("mid"))
                        for result in send_results
                        if result.get("send_future") is not None
                    ]
                else:
                    log_payload["process_status"] = "failed"
                    log_payload["decision_reason"] = "send_failed"
                    # 发送层（WebSocket 发送）就失败，直接判定发送失败
                    log_payload["send_status"] = "failed"
                    error_messages = [
                        str(result.get("error_message") or "").strip()
                        for result in failed_results
                        if result.get("error_message")
                    ]
                    if error_messages:
                        log_payload["error_message"] = "；".join(error_messages)
                        log_payload["send_fail_reason"] = "；".join(error_messages)
            elif not should_skip and log_payload.get("process_status") == "processing":
                log_payload["process_status"] = "skipped"
                log_payload["decision_reason"] = "no_rule_matched"

            api_error = log_payload.pop("_api_keyword_error", None)
            if api_error:
                # 错误提示发送成功不代表API调用或同步发货成功。
                log_payload.update(process_status="failed", decision_reason="failed", error_message=api_error)
                await self._unmark_chat_processed(chat_id, send_message)
            elif log_payload.pop("_api_confirmation_paused", False):
                # API文本已发出，但回执等待期间被人工暂停，确认阶段仍记为跳过。
                log_payload.update(process_status="skipped", decision_reason="chat_paused_after_delay")
            
            # 7. 发送消息通知(检查是否需要跳过)
            skip_notify_keywords = await self.get_filter_keywords('skip_notify')
            should_skip_notification = self.should_skip_notify(send_message, skip_notify_keywords)
            self._merge_log_context(
                log_payload,
                skip_notify_keywords=skip_notify_keywords,
                should_skip_notification=should_skip_notification,
            )
            
            if not should_skip_notification:
                await self._send_notification(
                    send_user_name=send_user_name,
                    send_user_id=send_user_id,
                    send_message=send_message,
                    chat_id=chat_id,
                    item_id=item_id,
                    msg_time=msg_time,
                )
            
        except asyncio.CancelledError:
            if api_handler is not None and log_payload.get("process_status") != "success":
                log_payload.update(process_status="failed", decision_reason="failed", error_message="API关键词处理被取消，可重新触发")
                await self._unmark_chat_processed(chat_id, send_message)
            raise
        except Exception as e:
            logger.exception("【{}】处理聊天消息失败", self.cookie_id)
            if api_handler is not None and log_payload.get("process_status") == "success":
                # 回复已成功时，通知等后续异常不能使成功日志失效，否则去重及额度会被绕过。
                log_payload.setdefault("context_snapshot", {})["api_keyword_post_reply_error"] = str(e)
            else:
                log_payload["process_status"] = "failed"
                log_payload["decision_reason"] = "failed"
                log_payload["error_message"] = str(e)
                if api_handler is not None:
                    await self._unmark_chat_processed(chat_id, send_message)
        finally:
            log_id = None
            try:
                log_payload.pop("_api_send_checked", None)
                log_payload.pop("_api_keyword_error", None)
                log_payload.pop("_api_confirmation_paused", None)
                # 取出待检测的发送 (future, mid)（临时键，不写入数据库）
                pending_send_waiters = log_payload.pop("_pending_send_waiters", None)
                ai_pause_log_recorded = log_payload.pop("_manual_reply_ai_pause_log_recorded", False)
                # AI 暂停后没有其他规则实际回复时，AI 暂停日志已单独写入，无需重复记录“未匹配规则”。
                should_skip_final_log = (
                    ai_pause_log_recorded
                    and log_payload.get("decision_reason") == "no_rule_matched"
                    and not pending_send_waiters
                )
                log_id = None if should_skip_final_log else await self._record_auto_reply_log(log_payload)
                # 若消息已发出且日志写入成功，起后台任务异步等待发送结果并回写状态
                if log_id and pending_send_waiters:
                    self._spawn_send_status_writeback(log_id, pending_send_waiters)
            finally:
                try:
                    if api_handler is not None:
                        try:
                            await api_handler.finalize_log(log_id)
                        finally:
                            await api_handler.close()
                finally:
                    self._reply_trace_var.reset(reply_trace_token)
