"""
自动回复服务

功能:
1. 关键词匹配回复(支持商品ID优先、图片类型)
2. AI回复
3. 默认回复(支持只回复一次)
4. 暂停状态检查
5. 变量替换
6. 消息过滤(跳过自动回复、跳过消息通知)

完全复刻原始XianyuAutoAsync.py中的自动回复逻辑
"""
from __future__ import annotations

import asyncio
import os
import time
import traceback
from typing import Optional, List, Dict, Any
from contextvars import ContextVar

from sqlalchemy import select, text, exists
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from common.models.xy_account import XYAccount
from common.models.xy_keyword_rule import XYKeywordRule
from common.models.xy_catalog_item import XYCatalogItem
from common.models.default_reply import DefaultReply, DefaultReplyRecord
from common.models.xy_order import XYOrder
from common.db.session import async_session_maker
from common.db.redis_client import distributed_lock
from common.utils.default_reply_api import call_reply_api

from app.services.xianyu.resource_manager import pause_manager
from app.services.xianyu.auto_reply_log_service import AutoReplyLogService
from app.services.xianyu.notification_dispatcher import NotificationDispatcher


class AutoReplyService:
    """自动回复服务
    
    按优先级处理:
    1. 检查系统消息(跳过不需要回复的系统消息)
    2. 检查消息过滤(跳过自动回复)
    3. 检查暂停状态
    4. 检查消息等待时间(去重)
    5. 关键词匹配(支持商品ID优先、图片类型)
    6. AI回复
    7. 默认回复(支持只回复一次)
    """
    
    # 需要跳过自动回复的系统消息列表（参照旧框架message_handler_core.py）
    # 这些消息不需要自动回复
    # 注意：评价消息需要单独处理自动评价，不在此处跳过
    SYSTEM_MESSAGES_TO_SKIP = [
        '[我已拍下，待付款]',
        '[你关闭了订单，钱款已原路退返]',
        '[不想宝贝被砍价?设置不砍价回复  ]',
        'AI正在帮你回复消息，不错过每笔订单',
        '发来一条消息',
        '发来一条新消息',
        '卖家人不错？送Ta闲鱼小红花',
        '你人真不错，送你闲鱼小红花',
        '[你已确认收货，交易成功]',
        '[买家确认收货，交易成功]',  # 确认收货消息由评价请求统一触发，此处跳过自动回复
        '买家已确认收货，交易成功',
        '[你已发货]',
        '已发货',
        '[注意！小心假客服骗钱！]',
        '「我将「退货退款」修改为「退款」」',
        '订单已签收',
        '有蚂蚁森林能量可领',
        # 评价相关消息（评价请求消息需要单独处理自动评价）
        # '快给ta一个评价吧~' 需要单独处理，不在此处跳过
        # '快给ta一个评价吧～' 需要单独处理，不在此处跳过
        '[我完成了评价]',
        '我完成了评价',
        # 退款相关消息
        '[退款成功，钱款已原路退返]',
        '[买家申请退款]',
        '[卖家同意退款]',
        # 系统提示消息
        '温馨提醒：商品信息近期有过变更',
        '查看商品详情',
    ]
    
    # 自动发货触发关键词（参照旧框架utils.py）
    # 这些消息应该触发自动发货，而不是自动回复
    AUTO_DELIVERY_KEYWORDS = [
        '[我已付款，等待你发货]',
        '[已付款，待发货]',
        '我已付款，等待你发货',
        '[记得及时发货]',
    ]
    
    def __init__(self, cookie_id: str, xianyu_instance):
        """
        初始化自动回复服务
        
        Args:
            cookie_id: 账号标识
            xianyu_instance: XianyuAsync实例(用于发送消息)
        """
        self.cookie_id = cookie_id
        self.xianyu_instance = xianyu_instance
        self.auto_reply_log_service = AutoReplyLogService(cookie_id)
        self.notification_dispatcher = NotificationDispatcher()
        self._account: Optional[XYAccount] = None
        # 消息过滤关键词缓存
        self._filter_keywords_cache: Dict[str, List[str]] = {}
        self._filter_cache_time: Dict[str, float] = {}  # 每个缓存键的时间
        self._filter_cache_ttl: float = 60  # 缓存有效期(秒)
        self._filter_cache_max_size: int = 1000  # 最大缓存条数
        
        # 关键词缓存（30秒TTL）
        self._keyword_cache: Dict[str, tuple] = {}  # cache_key -> (keywords, timestamp)
        self._keyword_cache_ttl: float = 30.0  # 缓存有效期(秒)
        
        # 消息去重(参照旧框架reply_scheduler.py)
        # 使用 chat_id + send_message 作为去重键，同一会话的同一消息内容在等待时间内不重复回复
        import asyncio
        self._processed_messages: Dict[str, float] = {}  # (chat_id + send_message) -> 最后回复时间
        self._processed_messages_lock = asyncio.Lock()
        self._processed_messages_max_size = 10000
        self._message_expire_time: Optional[int] = None  # 从数据库加载
        self._message_expire_time_loaded = False
        self._reply_trace_var: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
            f"auto_reply_trace_{cookie_id}",
            default=None,
        )
    
    async def _get_account(self, session: AsyncSession) -> Optional[XYAccount]:
        """获取账号信息(带缓存)"""
        if self._account is None:
            stmt = select(XYAccount).where(XYAccount.account_id == self.cookie_id)
            result = await session.execute(stmt)
            self._account = result.scalars().first()
        return self._account
    
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
    
    # ==================== 消息去重功能(参照旧框架reply_scheduler.py) ====================
    
    async def _load_message_expire_time(self) -> int:
        """从数据库加载消息等待时间配置"""
        if self._message_expire_time_loaded and self._message_expire_time is not None:
            return self._message_expire_time
        
        try:
            from common.db.compat import db_manager
            expire_time = db_manager.get_cookie_message_expire_time(self.cookie_id)
            if expire_time is not None and expire_time >= 0:
                self._message_expire_time = expire_time
                self._message_expire_time_loaded = True
                logger.info(f"【{self.cookie_id}】加载消息等待时间配置: {expire_time}秒")
                return expire_time
            self._message_expire_time = 3600
            self._message_expire_time_loaded = True
            return 3600
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】加载消息等待时间配置失败: {e}，使用默认值3600秒")
            self._message_expire_time = 3600
            self._message_expire_time_loaded = True
            return 3600
    
    async def _load_reply_delay(self) -> int:
        """实时从数据库加载自动回复延迟时间配置(秒)，0表示立即回复
        
        每次发送前都重新查库，保证账号管理中修改延迟时间后实时生效，无需重启账号。
        """
        try:
            async with async_session_maker() as session:
                stmt = select(XYAccount.reply_delay_seconds).where(
                    XYAccount.account_id == self.cookie_id
                )
                result = await session.execute(stmt)
                delay = result.scalar_one_or_none()
                if delay is not None and delay > 0:
                    return delay
                return 0
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】加载自动回复延迟配置失败: {e}，使用默认值0秒")
            return 0
    
    async def _check_chat_processed(self, chat_id: str, send_message: str) -> bool:
        """检查该会话的该消息是否在等待时间内已处理过(参照旧框架)
        
        Args:
            chat_id: 会话ID
            send_message: 消息内容
            
        Returns:
            True表示已处理过(应跳过),False表示可以处理
        """
        message_expire_time = await self._load_message_expire_time()
        
        # 如果配置为0，表示不限制
        if message_expire_time <= 0:
            return False
        
        # 使用 chat_id + send_message 作为去重键（参照旧框架）
        dedup_key = f"{chat_id}_{send_message}"
        
        async with self._processed_messages_lock:
            current_time = time.time()
            
            if dedup_key in self._processed_messages:
                last_process_time = self._processed_messages[dedup_key]
                time_elapsed = current_time - last_process_time
                
                if time_elapsed < message_expire_time:
                    remaining_time = int(message_expire_time - time_elapsed)
                    logger.warning(f"【{self.cookie_id}】消息 '{send_message[:30]}...' 已处理过，距离可重复回复还需 {remaining_time} 秒")
                    return True
                else:
                    logger.info(f"【{self.cookie_id}】消息 '{send_message[:30]}...' 已超过 {int(time_elapsed)} 秒，允许重新回复")
            
            return False
    
    async def _mark_chat_processed(self, chat_id: str, send_message: str) -> None:
        """标记该会话的该消息已处理(参照旧框架)
        
        Args:
            chat_id: 会话ID
            send_message: 消息内容
        """
        message_expire_time = await self._load_message_expire_time()
        
        # 使用 chat_id + send_message 作为去重键（参照旧框架）
        dedup_key = f"{chat_id}_{send_message}"
        
        async with self._processed_messages_lock:
            current_time = time.time()
            self._processed_messages[dedup_key] = current_time
            
            # 清理过期记录
            if len(self._processed_messages) > self._processed_messages_max_size:
                expired_keys = [
                    key for key, timestamp in self._processed_messages.items()
                    if current_time - timestamp > message_expire_time
                ]
                
                for key in expired_keys:
                    del self._processed_messages[key]
                
                if expired_keys:
                    logger.info(f"【{self.cookie_id}】清理了 {len(expired_keys)} 个过期消息记录")
                
                # 如果清理后仍然过大，删除最旧的一半
                if len(self._processed_messages) > self._processed_messages_max_size:
                    sorted_keys = sorted(self._processed_messages.items(), key=lambda x: x[1])
                    remove_count = len(sorted_keys) // 2
                    for key, _ in sorted_keys[:remove_count]:
                        del self._processed_messages[key]
                    logger.info(f"【{self.cookie_id}】消息去重字典过大，已清理 {remove_count} 个最旧记录")
    
    # ==================== 系统消息检查功能（参照旧框架message_handler_core.py） ====================
    
    def is_system_message_to_skip(self, send_message: str) -> bool:
        """检查是否为需要跳过自动回复的系统消息
        
        参照旧框架message_handler_core.py的is_system_message_to_skip方法
        
        Args:
            send_message: 消息内容
            
        Returns:
            True表示应该跳过自动回复,False表示正常处理
        """
        # 精确匹配
        if send_message in self.SYSTEM_MESSAGES_TO_SKIP:
            logger.info(f"【{self.cookie_id}】系统消息不处理自动回复(精确匹配): {send_message}")
            return True
        
        # 包含匹配（处理消息内容可能有细微差异的情况）
        # 只检查系统消息是否包含在用户消息中，不反向检查
        for skip_msg in self.SYSTEM_MESSAGES_TO_SKIP:
            if skip_msg in send_message:
                logger.info(f"【{self.cookie_id}】系统消息不处理自动回复(包含匹配): {send_message}")
                return True
        
        return False
    
    def is_auto_delivery_trigger(self, send_message: str) -> bool:
        """检查是否为自动发货触发消息
        
        参照旧框架utils.py的is_auto_delivery_trigger方法
        这些消息应该触发自动发货流程，而不是自动回复
        
        Args:
            send_message: 消息内容
            
        Returns:
            True表示是自动发货触发消息,False表示不是
        """
        for keyword in self.AUTO_DELIVERY_KEYWORDS:
            if keyword in send_message:
                logger.info(f"【{self.cookie_id}】检测到自动发货触发消息: {send_message}")
                return True
        return False
    
    def is_rate_request_message(self, send_message: str) -> bool:
        """检查是否为评价请求消息
        
        参照旧框架message_handler_core.py的is_rate_request_message方法
        这些消息应该触发自动评价流程
        
        Args:
            send_message: 消息内容
            
        Returns:
            True表示是评价请求消息,False表示不是
        """
        rate_keywords = ['快给ta一个评价吧~', '快给ta一个评价吧～']
        return send_message in rate_keywords
    
    def is_confirm_receipt_message(self, send_message: str) -> bool:
        """检查是否为确认收货消息
        
        这些消息应该触发确认收货回复流程
        注意：必须在评价消息检查之后调用，因为确认收货后会紧接着收到评价请求消息
        
        Args:
            send_message: 消息内容
            
        Returns:
            True表示是确认收货消息,False表示不是
        """
        confirm_receipt_keywords = [
            '[买家确认收货，交易成功]',
            '买家已确认收货，交易成功',
        ]
        for keyword in confirm_receipt_keywords:
            if keyword in send_message:
                return True
        return False
    
    # ==================== 消息过滤功能 ====================
    
    async def get_filter_keywords(self, filter_type: str = 'skip_reply') -> List[str]:
        """获取消息过滤关键词列表
        
        Args:
            filter_type: 过滤类型 'skip_reply'(跳过自动回复) 或 'skip_notify'(跳过消息通知)
            
        Returns:
            关键词列表
        """
        current_time = time.time()
        
        # 检查缓存是否有效
        cache_key = f"{self.cookie_id}_{filter_type}"
        cache_time = self._filter_cache_time.get(cache_key, 0)
        if (cache_key in self._filter_keywords_cache and 
            current_time - cache_time < self._filter_cache_ttl):
            return self._filter_keywords_cache.get(cache_key, [])
        
        # 从数据库查询
        try:
            async with async_session_maker() as session:
                logger.debug(f"【{self.cookie_id}】查询消息过滤关键词: account_id={self.cookie_id}, filter_type={filter_type}")
                result = await session.execute(
                    text("""
                        SELECT keyword FROM xy_message_filters 
                        WHERE account_id = :account_id 
                        AND filter_type = :filter_type 
                        AND enabled = 1
                    """),
                    {"account_id": self.cookie_id, "filter_type": filter_type}
                )
                rows = result.fetchall()
                keywords = [row.keyword for row in rows]
                
                # 清理过期缓存（当缓存过大时）
                if len(self._filter_keywords_cache) > self._filter_cache_max_size:
                    expired_keys = [
                        k for k, t in self._filter_cache_time.items()
                        if current_time - t > self._filter_cache_ttl
                    ]
                    for k in expired_keys:
                        self._filter_keywords_cache.pop(k, None)
                        self._filter_cache_time.pop(k, None)
                    if expired_keys:
                        logger.debug(f"【{self.cookie_id}】清理了 {len(expired_keys)} 个过期过滤关键词缓存")
                
                # 更新缓存
                self._filter_keywords_cache[cache_key] = keywords
                self._filter_cache_time[cache_key] = current_time
                
                logger.debug(f"【{self.cookie_id}】查询到{filter_type}过滤关键词: {keywords}")
                
                return keywords
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取消息过滤关键词失败: {e}")
            logger.error(traceback.format_exc())
            return []
    
    def should_skip_reply(self, message: str, filter_keywords: List[str]) -> bool:
        """检查消息是否应该跳过自动回复
        
        Args:
            message: 消息内容
            filter_keywords: 过滤关键词列表
            
        Returns:
            True表示应该跳过,False表示正常处理
        """
        if not filter_keywords or not message:
            return False
        
        message_lower = message.lower()
        for keyword in filter_keywords:
            if keyword.lower() in message_lower:
                logger.info(f"【{self.cookie_id}】消息匹配过滤关键词 '{keyword}'，跳过自动回复")
                return True
        
        return False
    
    def should_skip_notify(self, message: str, filter_keywords: List[str]) -> bool:
        """检查消息是否应该跳过消息通知
        
        Args:
            message: 消息内容
            filter_keywords: 过滤关键词列表
            
        Returns:
            True表示应该跳过,False表示正常处理
        """
        if not filter_keywords or not message:
            return False
        
        message_lower = message.lower()
        for keyword in filter_keywords:
            if keyword.lower() in message_lower:
                logger.info(f"【{self.cookie_id}】消息匹配过滤关键词 '{keyword}'，跳过消息通知")
                return True
        
        return False
    
    # ==================== 消息处理入口 ====================
    
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
                # 手动发出消息，暂停该会话的自动回复
                log_payload["process_status"] = "skipped"
                log_payload["decision_reason"] = "self_message"
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
                from app.services.xianyu.rate_service import check_item_belongs_to_account
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
            
            # 5. 检查消息等待时间(去重，参照旧框架reply_scheduler.py)
            # 同一会话的同一消息内容在等待时间内不重复回复
            if await self._check_chat_processed(chat_id, send_message):
                logger.info(f"【{self.cookie_id}】消息 '{send_message[:30]}...' 在等待时间内已处理过，跳过自动回复")
                log_payload["process_status"] = "skipped"
                log_payload["decision_reason"] = "duplicate_message"
                return
            
            # 6. 检查消息过滤(跳过自动回复)
            skip_reply_keywords = await self.get_filter_keywords('skip_reply')
            logger.debug(f"【{self.cookie_id}】消息过滤关键词: {skip_reply_keywords}")
            should_skip = self.should_skip_reply(send_message, skip_reply_keywords)
            self._merge_log_context(
                log_payload,
                skip_reply_keywords=skip_reply_keywords,
                should_skip_reply=should_skip,
            )
            logger.debug(f"【{self.cookie_id}】消息过滤结果: should_skip={should_skip}, message={send_message[:30]}")
            
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
                )
                
                if reply:
                    # 标记该消息已处理(在发送回复前标记，参照旧框架)
                    await self._mark_chat_processed(chat_id, send_message)
                    
                    # 自动回复延迟：按账号配置在发送前等待指定秒数
                    reply_delay = await self._load_reply_delay()
                    if reply_delay > 0:
                        logger.info(f"【{self.cookie_id}】自动回复延迟 {reply_delay} 秒后发送")
                        await asyncio.sleep(reply_delay)
                    
                    # 检查是否是图片发送指令
                    # 格式：__IMAGE_SEND__|类型标识|image_url
                    # 类型标识：KW:keyword（关键词）、DR:item_id（默认回复）、空（不需要更新）
                    if reply.startswith("__IMAGE_SEND__"):
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
                    # 消息已发出 WebSocket，但是否被服务端接收需异步等待响应确认，
                    # 先置为 unknown，由后台任务在拿到响应后回写 success/failed
                    log_payload["send_status"] = "unknown"
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
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】处理聊天消息失败: {e}")
            log_payload["process_status"] = "failed"
            log_payload["decision_reason"] = "failed"
            log_payload["error_message"] = str(e)
        finally:
            try:
                # 取出待检测的发送 (future, mid)（临时键，不写入数据库）
                pending_send_waiters = log_payload.pop("_pending_send_waiters", None)
                log_id = await self._record_auto_reply_log(log_payload)
                # 若消息已发出且日志写入成功，起后台任务异步等待发送结果并回写状态
                if log_id and pending_send_waiters:
                    self._spawn_send_status_writeback(log_id, pending_send_waiters)
            finally:
                self._reply_trace_var.reset(reply_trace_token)

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
                import asyncio
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
    ) -> List[Dict[str, Any]]:
        """发送文本消息，支持 ###### 分隔符拆分为多条消息（参照旧框架）
        
        Args:
            websocket: WebSocket连接
            chat_id: 会话ID
            send_user_id: 接收者用户ID
            text: 消息内容
        """
        import asyncio
        send_results: List[Dict[str, Any]] = []
         
        # 检查是否包含分隔符
        if '######' in text:
            messages = [msg.strip() for msg in text.split('######') if msg.strip()]
            logger.info(f"【{self.cookie_id}】检测到分隔符，拆分为 {len(messages)} 条消息")
             
            for i, msg in enumerate(messages):
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
        """发送消息通知（委托 NotificationDispatcher 进行渠道分发）
        
        Args:
            send_user_name: 发送者用户名
            send_user_id: 发送者用户ID
            send_message: 消息内容
            chat_id: 会话ID
            item_id: 商品ID
            msg_time: 消息时间
        """
        try:
            from common.db.compat import db_manager
            
            # 获取账号的通知配置(使用get_account_notifications方法)
            notifications = db_manager.get_account_notifications(self.cookie_id)
            if not notifications:
                logger.debug(f"【{self.cookie_id}】未配置消息通知，跳过通知发送")
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
            notification_content = f"【闲鱼消息】\n"
            notification_content += f"闲鱼账号: {account_desc}\n"
            notification_content += f"发送者: {send_user_name}\n"
            notification_content += f"消息: {send_message}\n"
            if item_id:
                notification_content += f"商品ID: {item_id}\n"
            notification_content += f"时间: {msg_time}"
            
            # 委托 NotificationDispatcher 并行发送到所有渠道（带错误隔离）
            await self.notification_dispatcher.dispatch_all(
                notifications, notification_content
            )
                    
        except Exception as e:
            logger.error(f"【{self.cookie_id}】发送消息通知失败: {e}")
    
    # ==================== 自动回复核心逻辑 ====================
    
    async def get_reply(
        self,
        send_user_name: str,
        send_user_id: str,
        send_message: str,
        chat_id: str,
        item_id: Optional[str] = None,
    ) -> Optional[str]:
        """获取自动回复(主入口)
        
        按优先级: 关键词 > AI > 默认回复
        
        Args:
            send_user_name: 发送者用户名
            send_user_id: 发送者用户ID
            send_message: 发送的消息内容
            chat_id: 会话ID
            item_id: 商品ID(可选)
            
        Returns:
            回复内容,None表示不回复
        """
        reply_trace = self._reply_trace_var.get()
        try:
            if pause_manager.is_chat_paused(chat_id, self.cookie_id):
                remaining = pause_manager.get_remaining_pause_time(chat_id, self.cookie_id)
                logger.info(f"【{self.cookie_id}】chat_id {chat_id} 自动回复暂停中,剩余 {remaining} 秒")
                if reply_trace is not None:
                    reply_trace["process_status"] = "skipped"
                    reply_trace["decision_reason"] = "chat_paused"
                    reply_trace.setdefault("context_snapshot", {})["pause_remaining_seconds"] = remaining
                return None
            
            async with async_session_maker() as session:
                keyword_reply = await self.get_keyword_reply(
                    session, send_user_name, send_user_id, send_message, item_id
                )
                if keyword_reply:
                    if keyword_reply == "EMPTY_REPLY":
                        if reply_trace is not None:
                            reply_trace["process_status"] = "skipped"
                            reply_trace["decision_reason"] = "empty_reply"
                        return None
                    return keyword_reply
                
                ai_reply = await self.get_ai_reply(
                    session, send_user_name, send_user_id, send_message, item_id, chat_id
                )
                if ai_reply:
                    return ai_reply
                
                default_reply = await self.get_default_reply(
                    session, send_user_name, send_user_id, send_message, chat_id, item_id
                )
                if default_reply:
                    if default_reply == "EMPTY_REPLY":
                        if reply_trace is not None:
                            reply_trace["process_status"] = "skipped"
                            reply_trace["decision_reason"] = "empty_reply"
                        return None
                    return default_reply
            
            if reply_trace is not None:
                reply_trace["process_status"] = "skipped"
                reply_trace["decision_reason"] = "no_rule_matched"
            return None
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取自动回复失败: {e}")
            if reply_trace is not None:
                reply_trace["process_status"] = "failed"
                reply_trace["decision_reason"] = "failed"
                reply_trace["error_message"] = str(e)
            return None
    
    async def get_keyword_reply(
        self,
        session: AsyncSession,
        send_user_name: str,
        send_user_id: str,
        send_message: str,
        item_id: Optional[str] = None,
    ) -> Optional[str]:
        """获取关键词匹配回复
        
        支持:
        - 商品ID优先匹配
        - 图片类型关键词
        - 变量替换
        
        Args:
            session: 数据库会话
            send_user_name: 发送者用户名
            send_user_id: 发送者用户ID
            send_message: 发送的消息内容
            item_id: 商品ID(可选)
            
        Returns:
            回复内容,None表示无匹配,"EMPTY_REPLY"表示匹配但回复为空
        """
        reply_trace = self._reply_trace_var.get()
        try:
            account = await self._get_account(session)
            if not account:
                return None
            
            keywords = await self._list_keywords(session, account)
            if not keywords:
                logger.debug(f"账号 {self.cookie_id} 没有配置关键词")
                return None
            
            msg_lower = send_message.lower()
            
            if item_id:
                for kw in keywords:
                    keyword = kw.get("keyword", "")
                    reply = kw.get("reply", "")
                    kw_item_id = kw.get("item_id", "")
                    kw_type = kw.get("type", "text")
                    image_url = kw.get("image_url", "")
                    
                    if kw_item_id == item_id and keyword.lower() in msg_lower:
                        logger.info(f"商品ID关键词匹配成功: 商品{item_id} '{keyword}' (类型: {kw_type})")
                        if reply_trace is not None:
                            reply_trace["reply_strategy"] = "keyword"
                            reply_trace["matched_keyword"] = keyword
                            reply_trace["matched_rule_type"] = "keyword_item"
                            reply_trace.setdefault("context_snapshot", {})["matched_item_title"] = kw.get("item_title") or None
                        
                        if kw_type == "image" and image_url:
                            image_reply = await self._handle_image_keyword(keyword, image_url)
                            if reply_trace is not None:
                                if image_reply.startswith("__IMAGE_SEND__"):
                                    reply_trace["reply_mode"] = "image"
                                    reply_trace["reply_image_url"] = image_url
                                    reply_trace["reply_segments"] = [{"mode": "image", "content": image_url, "index": 1}]
                                else:
                                    reply_trace["reply_mode"] = "text"
                                    reply_trace["reply_text"] = image_reply
                                    reply_trace["reply_segments"] = self._build_text_reply_segments(image_reply)
                            return image_reply
                        
                        if not reply or not reply.strip():
                            logger.info(f"商品ID关键词 '{keyword}' 回复内容为空,不进行回复")
                            return "EMPTY_REPLY"
                        
                        try:
                            formatted = reply.format(
                                send_user_name=send_user_name,
                                send_user_id=send_user_id,
                                send_message=send_message,
                                item_id=item_id or "",
                            )
                            logger.info(f"商品ID文本关键词回复: {formatted}")
                            if reply_trace is not None:
                                reply_trace["reply_mode"] = "text"
                                reply_trace["reply_text"] = formatted
                                reply_trace["reply_segments"] = self._build_text_reply_segments(formatted)
                            return formatted
                        except Exception as e:
                            logger.error(f"关键词回复变量替换失败: {e}")
                            if reply_trace is not None:
                                reply_trace["reply_mode"] = "text"
                                reply_trace["reply_text"] = reply
                                reply_trace["reply_segments"] = self._build_text_reply_segments(reply)
                                reply_trace.setdefault("context_snapshot", {})["keyword_format_error"] = str(e)
                            return reply
            
            for kw in keywords:
                keyword = kw.get("keyword", "")
                reply = kw.get("reply", "")
                kw_item_id = kw.get("item_id", "")
                kw_type = kw.get("type", "text")
                image_url = kw.get("image_url", "")

                if not kw_item_id and keyword.lower() in msg_lower:
                    logger.info(f"通用关键词匹配成功: '{keyword}' (类型: {kw_type})")
                    if reply_trace is not None:
                        reply_trace["reply_strategy"] = "keyword"
                        reply_trace["matched_keyword"] = keyword
                        reply_trace["matched_rule_type"] = "keyword_common"

                    if kw_type == "image" and image_url:
                        image_reply = await self._handle_image_keyword(keyword, image_url)
                        if reply_trace is not None:
                            if image_reply.startswith("__IMAGE_SEND__"):
                                reply_trace["reply_mode"] = "image"
                                reply_trace["reply_image_url"] = image_url
                                reply_trace["reply_segments"] = [{"mode": "image", "content": image_url, "index": 1}]
                            else:
                                reply_trace["reply_mode"] = "text"
                                reply_trace["reply_text"] = image_reply
                                reply_trace["reply_segments"] = self._build_text_reply_segments(image_reply)
                        return image_reply

                    if not reply or not reply.strip():
                        logger.info(f"通用关键词 '{keyword}' 回复内容为空,不进行回复")
                        return "EMPTY_REPLY"

                    try:
                        formatted = reply.format(
                            send_user_name=send_user_name,
                            send_user_id=send_user_id,
                            send_message=send_message,
                            item_id=item_id or "",
                        )
                        logger.info(f"通用文本关键词回复: {formatted}")
                        if reply_trace is not None:
                            reply_trace["reply_mode"] = "text"
                            reply_trace["reply_text"] = formatted
                            reply_trace["reply_segments"] = self._build_text_reply_segments(formatted)
                        return formatted
                    except Exception as e:
                        logger.error(f"关键词回复变量替换失败: {e}")
                        if reply_trace is not None:
                            reply_trace["reply_mode"] = "text"
                            reply_trace["reply_text"] = reply
                            reply_trace["reply_segments"] = self._build_text_reply_segments(reply)
                            reply_trace.setdefault("context_snapshot", {})["keyword_format_error"] = str(e)
                        return reply

            logger.debug(f"未找到匹配的关键词: {send_message[:30]}...")
            return None

        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取关键词回复失败: {e}")
            return None

    async def _list_keywords(self, session: AsyncSession, account: XYAccount) -> list[dict]:
        """获取关键词列表（参照旧框架，添加is_active条件，带30秒TTL缓存）"""
        cache_key = f"kw_{account.id}"
        now = time.time()
        
        # 检查缓存
        if cache_key in self._keyword_cache:
            cached_keywords, cached_time = self._keyword_cache[cache_key]
            if now - cached_time < self._keyword_cache_ttl:
                return cached_keywords
        
        stmt = (
            select(XYKeywordRule, XYCatalogItem.title)
            .outerjoin(
                XYCatalogItem,
                (XYCatalogItem.account_pk == XYKeywordRule.account_pk)
                & (XYCatalogItem.item_id == XYKeywordRule.item_id),
            )
            .where(
                XYKeywordRule.account_pk == account.id,
                XYKeywordRule.is_active == True,  # 参照旧框架，只查询启用的关键词
            )
            .order_by(XYKeywordRule.keyword, XYKeywordRule.item_id)
        )
        rows = await session.execute(stmt)
        keywords: list[dict] = []
        for rule, item_title in rows.all():
            rule_type = (rule.reply_type or "text").lower()
            keywords.append(
                {
                    "keyword": rule.keyword,
                    "reply": rule.reply_content or "",
                    "item_id": rule.item_id or "",
                    "type": "image" if rule_type == "image" else "text",
                    "image_url": rule.image_url or "",
                    "item_title": item_title or "",
                }
            )
        
        # 写入缓存
        self._keyword_cache[cache_key] = (keywords, now)
        return keywords
    
    async def _handle_image_keyword(self, keyword: str, image_url: str) -> str:
        """处理图片类型关键词
        
        Args:
            keyword: 关键词
            image_url: 图片URL
            
        Returns:
            图片发送指令（格式：__IMAGE_SEND__|KW:keyword|image_url）或错误提示
        """
        try:
            if self._is_cdn_url(image_url):
                logger.info(f"使用已有的CDN图片链接: {image_url}")
                # CDN链接不需要更新
                return f"__IMAGE_SEND__||{image_url}"
            
            elif image_url.startswith("/static/uploads/") or image_url.startswith("static/uploads/"):
                # 使用STATIC_DIR环境变量（Docker共享卷），本地回退到backend-web/static
                from pathlib import Path
                _static_env = os.environ.get("STATIC_DIR", "")
                if _static_env:
                    static_root = Path(_static_env)
                    if not static_root.is_absolute():
                        static_root = Path.cwd() / static_root
                else:
                    static_root = Path(__file__).resolve().parent.parent.parent.parent.parent / "backend-web" / "static"
                # 转换URL路径为本地文件路径
                relative_path = image_url.lstrip('/').replace('static/', '', 1)
                local_path = str(static_root / relative_path)
                if os.path.exists(local_path):
                    logger.info(f"准备上传本地图片到闲鱼CDN: {local_path}")
                    # 本地图片需要上传，传递KW:keyword用于后续更新
                    return f"__IMAGE_SEND__|KW:{keyword}|{image_url}"
                else:
                    logger.error(f"本地图片文件不存在: {local_path}")
                    return "抱歉,图片文件不存在。"
            else:
                logger.info(f"使用外部图片链接: {image_url}")
                # 外部链接不需要更新
                return f"__IMAGE_SEND__||{image_url}"
                
        except Exception as e:
            logger.error(f"处理图片关键词失败: {e}")
            return f"抱歉,图片发送失败: {e}"
    
    def _is_cdn_url(self, url: str) -> bool:
        """检查是否是闲鱼CDN链接"""
        if not url:
            return False
        cdn_domains = [
            "gw.alicdn.com", "img.alicdn.com", "cloud.goofish.com",
            "goofish.com", "taobaocdn.com", "tbcdn.cn", "aliimg.com",
        ]
        url_lower = url.lower()
        return any(domain in url_lower for domain in cdn_domains)
    
    async def _do_api_default_reply(
        self,
        session: AsyncSession,
        send_message: str,
        api_url: str,
        api_timeout,
        settings: dict,
        settings_item_id: Optional[str],
        chat_id: str,
        reply_trace: Optional[dict],
    ) -> Optional[str]:
        """调用外部 API 获取默认回复内容并处理结果。

        由 get_default_reply 在持有会话级去重锁（或降级无锁）时调用：
        - 调用失败/超时/无有效内容：返回 None，不回复，且不记录 reply_once（便于下次重试）；
        - 调用成功：按需记录 reply_once，返回回复文本（下游按 ###### 分段发送）。
        """
        api_reply = await call_reply_api(
            account_id=self.cookie_id,
            message=send_message,
            api_url=api_url,
            timeout=api_timeout,
        )

        # 失败/无有效内容：不回复（不记录 reply_once，便于下次重试）
        if not api_reply or not api_reply.strip():
            logger.info(f"【{self.cookie_id}】默认回复API未返回有效内容,不进行回复")
            if reply_trace is not None:
                reply_trace["process_status"] = "skipped"
                reply_trace["decision_reason"] = "no_rule_matched"
                reply_trace.setdefault("context_snapshot", {})["default_reply_api_url"] = api_url
            return None

        # 调用成功后再记录 reply_once
        if settings.get("reply_once", False) and chat_id:
            await self._record_user_replied(session, self.cookie_id, chat_id, settings_item_id)
            logger.info(f"【{self.cookie_id}】记录默认回复(API): chat_id={chat_id}, item_id={settings_item_id}")

        logger.info(f"【{self.cookie_id}】使用API默认回复: {api_reply[:50]}")
        if reply_trace is not None:
            reply_trace["reply_mode"] = "text"
            reply_trace["reply_text"] = api_reply
            reply_trace["reply_segments"] = self._build_text_reply_segments(api_reply)
            reply_trace.setdefault("context_snapshot", {})["default_reply_api_url"] = api_url
        return api_reply

    async def get_default_reply(
        self,
        session: AsyncSession,
        send_user_name: str,
        send_user_id: str,
        send_message: str,
        chat_id: str,
        item_id: Optional[str] = None,
    ) -> Optional[str]:
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
            
        Returns:
            回复内容,None表示不回复,"EMPTY_REPLY"表示回复为空
        """
        reply_trace = self._reply_trace_var.get()
        try:
            settings = await self._get_default_reply_settings(session, self.cookie_id, item_id)
            
            if not settings or not settings.get("enabled", False):
                logger.debug(f"账号 {self.cookie_id} 未启用默认回复")
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
            from app.services.xianyu.ai_reply_engine import get_ai_reply_engine
            
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
                logger.debug(f"【{self.cookie_id}】AI回复未启用")
                return None

            ai_settings = await ai_engine.get_ai_settings(self.cookie_id, session)
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

            logger.debug(f"【{self.cookie_id}】AI回复生成失败或返回空")
            return None
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取AI回复失败: {e}")
            return None

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
