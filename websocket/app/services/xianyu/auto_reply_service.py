"""自动回复入口：关键词、API关键词、AI及默认回复。由自动回复入口组合，保持现有调用签名。"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.xianyu.auto_reply_ai import AutoReplyAiMixin
from app.services.xianyu.auto_reply_chat import AutoReplyChatMixin
from app.services.xianyu.auto_reply_defaults import AutoReplyDefaultsMixin
from app.services.xianyu.auto_reply_filters import AutoReplyFiltersMixin
from app.services.xianyu.auto_reply_keywords import AutoReplyKeywordsMixin
from app.services.xianyu.auto_reply_log_service import AutoReplyLogService
from app.services.xianyu.auto_reply_logs import AutoReplyLogsMixin
from app.services.xianyu.auto_reply_remote import AutoReplyRemoteMixin
from app.services.xianyu.resource_manager import pause_manager
from common.db.session import async_session_maker
from common.models.xy_account import XYAccount


class AutoReplyService(
    AutoReplyChatMixin, AutoReplyLogsMixin, AutoReplyFiltersMixin,
    AutoReplyKeywordsMixin, AutoReplyRemoteMixin, AutoReplyDefaultsMixin, AutoReplyAiMixin,
):
    """自动回复服务
    
    按优先级处理:
    1. 检查系统消息(跳过不需要回复的系统消息)
    2. 检查消息过滤(跳过自动回复)
    3. 检查暂停状态
    4. 检查消息等待时间(去重)
    5. 关键词匹配(支持商品ID优先、图片、站外联系方式及API类型)
    6. AI回复
    7. 默认回复(支持只回复一次)
    """

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

    AUTO_DELIVERY_KEYWORDS = [
        '[我已付款，等待你发货]',
        '[已付款，待发货]',
        '我已付款，等待你发货',
        '[记得及时发货]',
        # 上门自提订单的付款提醒（自提单不会出现"等待你发货"文案），同样需要触发发货
        '[我已付款，请添加自提信息]',
        '我已付款，请添加自提信息',
    ]

    KEYWORD_REPLY_TYPE_PRIORITY = {
        "image": 30,
        "external_contact": 20,
        "api_keyword": 15,
        "text": 10,
    }

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
        self._account: Optional[XYAccount] = None
        # 消息过滤关键词缓存
        self._filter_keywords_cache: Dict[str, List[str]] = {}
        self._filter_cache_time: Dict[str, float] = {}  # 每个缓存键的时间
        self._filter_cache_ttl: float = 60  # 缓存有效期(秒)
        self._filter_cache_max_size: int = 1000  # 最大缓存条数
        
        # 消息去重(参照旧框架reply_scheduler.py)
        # 使用 chat_id + send_message 作为去重键，同一会话的同一消息内容在等待时间内不重复回复
        self._processed_messages: Dict[str, float] = {}  # (chat_id + send_message) -> 最后回复时间
        self._processed_messages_lock = asyncio.Lock()
        self._processed_messages_max_size = 10000
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

    async def get_reply(
        self,
        send_user_name: str,
        send_user_id: str,
        send_message: str,
        chat_id: str,
        item_id: Optional[str] = None,
        msg_time: str = "",
    ) -> Optional[Any]:
        """获取自动回复(主入口)
        
        按优先级: 商品级关键词 > 通用关键词；同一范围内图片 > 站外联系方式 > API > 文本；
        未命中关键词后再依次尝试 AI 和默认回复
        
        Args:
            send_user_name: 发送者用户名
            send_user_id: 发送者用户ID
            send_message: 发送的消息内容
            chat_id: 会话ID
            item_id: 商品ID(可选)
            msg_time: 消息时间
            
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
                    session, send_user_name, send_user_id, send_message, item_id, chat_id
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
                    session, send_user_name, send_user_id, send_message, chat_id, item_id, msg_time
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
