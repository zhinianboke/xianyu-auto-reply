"""回复日志、发送及通知。由自动回复入口组合，保持现有调用签名。"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from common.db.compat import db_manager
from common.utils.notification_template import render_notification_template
from common.utils.notification_utils import (
    parse_notification_config,
    send_bark_notification,
    send_dingtalk_notification,
    send_email_notification,
    send_feishu_notification,
    send_pushplus_notification,
    send_telegram_notification,
    send_webhook_notification,
    send_wechat_notification,
)


class AutoReplyLogsMixin:
    """封装自动回复logs相关处理。"""

    def _build_auto_reply_log_payload(self, parsed_message: Dict[str, Any]) -> Dict[str, Any]:
        """构建自动回复日志基础数据"""
        send_message = parsed_message.get("send_message", "")
        chat_id = parsed_message.get("chat_id", "")
        return {
            "source_message_id": self._extract_source_message_id(parsed_message.get("raw_message")),
            "sender_user_id": parsed_message.get("send_user_id", ""),
            "sender_user_name": parsed_message.get("send_user_name", ""),
            "source_message": send_message,
            "chat_id": chat_id,
            "item_id": parsed_message.get("item_id") or None,
            "msg_time": parsed_message.get("msg_time"),
            "raw_message_json": parsed_message.get("raw_message"),
            "process_status": "processing",
            "decision_reason": "processing",
            "reply_strategy": "none",
            "reply_mode": "none",
            "default_reply_once": False,
            "reply_segments": [],
            "context_snapshot": {
                "dedup_key": f"{chat_id}_{send_message}" if chat_id or send_message else None,
            },
        }

    def _extract_source_message_id(self, raw_message: Any) -> Optional[str]:
        """提取源消息ID"""
        if not isinstance(raw_message, dict):
            return None
        message_handler = getattr(self.xianyu_instance, "message_handler", None)
        if not message_handler or not hasattr(message_handler, "extract_message_id"):
            return None
        try:
            return message_handler.extract_message_id(raw_message)
        except Exception:
            return None

    def _merge_log_context(self, log_payload: Dict[str, Any], **kwargs) -> None:
        """合并日志上下文快照"""
        context_snapshot = log_payload.setdefault("context_snapshot", {})
        for key, value in kwargs.items():
            if value is not None:
                context_snapshot[key] = value

    def _build_text_reply_segments(self, text: str) -> List[Dict[str, Any]]:
        """构建文本回复分段"""
        if not text:
            return []
        if "######" in text:
            messages = [msg.strip() for msg in text.split("######") if msg.strip()]
        else:
            messages = [text]
        return [
            {"mode": "text", "content": msg, "index": index + 1}
            for index, msg in enumerate(messages)
        ]

    def _parse_image_reply_command(self, reply: str) -> tuple[Optional[str], Optional[str], str]:
        """解析图片发送指令"""
        content = reply.replace("__IMAGE_SEND__", "", 1)
        if content.startswith("|"):
            content = content[1:]
        parts = content.split("|", 1)
        update_type: Optional[str] = None
        update_key: Optional[str] = None
        if len(parts) >= 2:
            type_part = parts[0]
            image_url = parts[1]
            if type_part.startswith("KW:"):
                update_type = "KW"
                update_key = type_part[3:]
            elif type_part.startswith("DR:"):
                update_type = "DR"
                update_key = type_part[3:] or None
            else:
                update_type = "KW" if type_part else None
                update_key = type_part if type_part else None
        else:
            image_url = parts[0] if parts else content
        return update_type, update_key, image_url

    def _build_empty_send_result(self, mode: str, content: str) -> Dict[str, Any]:
        """构建空发送结果兜底值"""
        result: Dict[str, Any] = {
            "success": False,
            "mode": mode,
            "error_message": "发送结果为空",
        }
        if mode == "image":
            result["image_url"] = content
        else:
            result["content"] = content
        return result

    def _is_send_results_success(self, send_results: List[Dict[str, Any]]) -> bool:
        """判断发送结果是否全部成功"""
        return bool(send_results) and all(bool(result.get("success")) for result in send_results)

    def _get_send_error_message(self, send_results: List[Dict[str, Any]]) -> Optional[str]:
        """提取发送失败原因"""
        if not send_results:
            return "发送结果为空"
        errors = [
            str(result.get("error_message") or "发送失败")
            for result in send_results
            if not result.get("success")
        ]
        if not errors:
            return None
        return "；".join(errors[:3])

    async def _record_auto_reply_log(self, log_payload: Dict[str, Any]) -> int | None:
        """写入自动回复日志，返回日志主键ID（供异步回写发送状态）"""
        return await self.auto_reply_log_service.record_message(log_payload)

    async def _record_manual_reply_ai_paused_log(
        self, log_payload: Dict[str, Any], remaining_seconds: int, pause_minutes: int
    ) -> None:
        """记录人工回复暂停 AI 的消息日志，不影响后续默认回复。"""
        pause_end_time = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(time.time() + remaining_seconds),
        )
        context_snapshot = dict(log_payload.get("context_snapshot") or {})
        context_snapshot.update({
            "manual_reply_ai_pause_remaining_seconds": remaining_seconds,
            "manual_reply_ai_pause_ends_at": pause_end_time,
            "manual_reply_ai_pause_buyer_id": log_payload.get("sender_user_id"),
            "manual_reply_ai_pause_item_id": log_payload.get("item_id") or "",
        })
        paused_log_payload = {
            **log_payload,
            "process_status": "skipped",
            "decision_reason": "manual_reply_ai_paused",
            "reply_strategy": "ai",
            "reply_mode": "none",
            "matched_rule_type": "ai",
            "reply_text": None,
            "reply_image_url": None,
            "reply_segments": [],
            "send_status": "paused",
            "send_fail_reason": (
                f"暂停ai回复{pause_minutes}分钟，预计恢复时间：{pause_end_time}"
            ),
            "send_result_json": None,
            "context_snapshot": context_snapshot,
        }
        await self._record_auto_reply_log(paused_log_payload)

    def _spawn_send_status_writeback(self, log_id: int, waiters: list) -> None:
        """起后台任务：异步等待发送结果并回写日志的发送状态

        不阻塞自动回复主流程。优先用实例的任务追踪器创建任务，
        不可用时回退到 asyncio.create_task。

        Args:
            log_id: 日志主键ID
            waiters: 本次发出消息的 (send_future, mid) 列表
        """
        try:
            coro = self._writeback_send_status(log_id, waiters)
            tracker = getattr(self.xianyu_instance, "_create_tracked_task", None)
            if callable(tracker):
                tracker(coro)
            else:
                asyncio.create_task(coro)
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】启动发送状态回写任务失败 log_id={log_id}: {e}")

    async def _writeback_send_status(self, log_id: int, waiters: list) -> None:
        """等待各发送响应，按结果回写日志发送状态

        - 任一消息被服务端拦截（返回 reason）→ send_status=failed，记录失败原因
        - 全部无拦截响应（含正常发送、超时）→ send_status=success

        Args:
            log_id: 日志主键ID
            waiters: 本次发出消息的 (send_future, mid) 列表
        """
        try:
            wait_fn = getattr(self.xianyu_instance, "wait_send_reject_reason", None)
            if not callable(wait_fn):
                return
            reasons: List[str] = []
            for send_future, mid in waiters:
                reason = await wait_fn(send_future, mid)
                if reason:
                    reasons.append(reason)
            if reasons:
                await self.auto_reply_log_service.safe_update_send_status(
                    log_id, "failed", "；".join(reasons)
                )
                logger.warning(
                    f"【{self.cookie_id}】自动回复发送被拦截 log_id={log_id}: {'；'.join(reasons)}"
                )
            else:
                await self.auto_reply_log_service.safe_update_send_status(log_id, "success", None)
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】回写发送状态异常 log_id={log_id}: {e}")

    async def _send_text_with_separator(
        self,
        websocket,
        chat_id: str,
        send_user_id: str,
        text: str,
        before_send=None,
    ) -> List[Dict[str, Any]]:
        """发送文本消息，支持 ###### 分隔符拆分为多条消息（参照旧框架）
        
        Args:
            websocket: WebSocket连接
            chat_id: 会话ID
            send_user_id: 接收者用户ID
            text: 消息内容
            before_send: 可选异步检查，每段实际发送前执行；失败停止后续发送。
        """
        send_results: List[Dict[str, Any]] = []
         
        # 检查是否包含分隔符
        if '######' in text:
            messages = [msg.strip() for msg in text.split('######') if msg.strip()]
            logger.info(f"【{self.cookie_id}】检测到分隔符，拆分为 {len(messages)} 条消息")
             
            for i, msg in enumerate(messages):
                if before_send is not None:
                    await before_send()
                result = await self.xianyu_instance.send_msg(
                    websocket=websocket,
                    chat_id=chat_id,
                    send_user_id=send_user_id,
                    content=msg,
                )
                send_results.append(result or self._build_empty_send_result("text", msg))
                logger.info(f"【{self.cookie_id}】发送文本回复 {i+1}/{len(messages)}: {msg[:50]}...")
                 
                # 多条消息之间添加短暂延迟
                if i < len(messages) - 1:
                    await asyncio.sleep(0.5)
        else:
            # 单条消息直接发送
            if before_send is not None:
                await before_send()
            result = await self.xianyu_instance.send_msg(
                websocket=websocket,
                chat_id=chat_id,
                send_user_id=send_user_id,
                content=text,
            )
            send_results.append(result or self._build_empty_send_result("text", text))
            logger.info(f"【{self.cookie_id}】发送文本回复: {text[:50]}...")

        return send_results

    async def _send_notification(
        self,
        send_user_name: str,
        send_user_id: str,
        send_message: str,
        chat_id: str,
        item_id: str,
        msg_time: str,
    ) -> None:
        """发送消息通知
        
        Args:
            send_user_name: 发送者用户名
            send_user_id: 发送者用户ID
            send_message: 消息内容
            chat_id: 会话ID
            item_id: 商品ID
            msg_time: 消息时间
        """
        try:
            
            # 获取账号的通知配置(使用get_account_notifications方法)
            notifications = db_manager.get_account_notifications(self.cookie_id)
            if not notifications:
                logger.info(f"【{self.cookie_id}】未配置消息通知，跳过通知发送")
                return
            
            # 获取账号备注
            remark = ""
            try:
                account_details = db_manager.get_cookie_details(self.cookie_id)
                if account_details:
                    remark = account_details.get("remark") or ""
            except Exception as e:
                logger.warning(f"获取账号详情失败: {e}")

            # 构建通知内容
            account_desc = f"{self.cookie_id}({remark})" if remark else self.cookie_id
            notification_content = "【闲鱼消息】\n"
            notification_content += f"闲鱼账号: {account_desc}\n"
            notification_content += f"发送者: {send_user_name}\n"
            notification_content += f"消息: {send_message}\n"
            if item_id:
                notification_content += f"商品ID: {item_id}\n"
            notification_content += f"时间: {msg_time}"
            template_context = {
                "account": account_desc,
                "account_id": self.cookie_id,
                "account_remark": remark or "未知",
                "buyer_nick": send_user_name or "未知",
                "buyer_id": send_user_id or "未知",
                "message": send_message or "",
                "item_id": item_id or "未知",
                "chat_id": chat_id or "未知",
                "time": msg_time or time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            
            # 发送通知到各渠道
            for notification in notifications:
                try:
                    # 检查通知是否启用
                    if not notification.get('enabled', True):
                        continue
                    
                    channel_type = notification.get('channel_type', '')
                    channel_config = notification.get('channel_config', {}) or {}
                    
                    # 使用公共通知工具函数
                    
                    config_data = parse_notification_config(channel_config)
                    channel_message = render_notification_template(
                        config_data,
                        "chat",
                        template_context,
                        notification_content,
                    )
                    
                    if channel_type in ('dingtalk', 'ding_talk'):
                        await send_dingtalk_notification(config_data, channel_message)
                    elif channel_type in ('feishu', 'lark'):
                        await send_feishu_notification(config_data, channel_message)
                    elif channel_type == 'bark':
                        await send_bark_notification(config_data, channel_message)
                    elif channel_type == 'email':
                        await send_email_notification(config_data, channel_message)
                    elif channel_type == 'webhook':
                        await send_webhook_notification(config_data, channel_message)
                    elif channel_type in ('wechat', 'wechat_work'):
                        await send_wechat_notification(config_data, channel_message)
                    elif channel_type == 'telegram':
                        await send_telegram_notification(config_data, channel_message)
                    elif channel_type == 'pushplus':
                        await send_pushplus_notification(config_data, channel_message)
                    else:
                        logger.warning(f"【{self.cookie_id}】不支持的通知渠道类型: {channel_type}")
                        
                except Exception as e:
                    logger.error(f"【{self.cookie_id}】发送{channel_type}通知失败: {e}")
                    
        except Exception as e:
            logger.error(f"【{self.cookie_id}】发送消息通知失败: {e}")
