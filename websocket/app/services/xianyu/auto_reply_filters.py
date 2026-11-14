"""消息去重与过滤。由自动回复入口组合，保持现有调用签名。"""
from __future__ import annotations

import time
import traceback
from typing import List

from loguru import logger
from sqlalchemy import select, text

from common.db.session import async_session_maker
from common.models.xy_account import XYAccount


class AutoReplyFiltersMixin:
    """封装自动回复filters相关处理。"""

    async def _load_message_expire_time(self) -> int:
        """实时从数据库加载消息等待时间配置

        每次调用都重新查库，保证账号管理中修改消息等待时间后实时生效，无需重启账号。
        """
        try:
            async with async_session_maker() as session:
                stmt = select(XYAccount.message_expire_time).where(
                    XYAccount.account_id == self.cookie_id
                )
                result = await session.execute(stmt)
                expire_time = result.scalar_one_or_none()
                if expire_time is not None and expire_time >= 0:
                    return expire_time
                return 3600
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】加载消息等待时间配置失败: {e}，使用默认值3600秒")
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

    async def _unmark_chat_processed(self, chat_id: str, send_message: str) -> None:
        """发送失败时撤销本次临时去重标记，允许后续消息重试。"""
        dedup_key = f"{chat_id}_{send_message}"
        async with self._processed_messages_lock:
            self._processed_messages.pop(dedup_key, None)

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
                logger.info(f"【{self.cookie_id}】查询消息过滤关键词: account_id={self.cookie_id}, filter_type={filter_type}")
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
                        logger.info(f"【{self.cookie_id}】清理了 {len(expired_keys)} 个过期过滤关键词缓存")
                
                # 更新缓存
                self._filter_keywords_cache[cache_key] = keywords
                self._filter_cache_time[cache_key] = current_time
                
                logger.info(f"【{self.cookie_id}】查询到{filter_type}过滤关键词: {keywords}")
                
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
