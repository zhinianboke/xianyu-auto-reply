"""
AI对话服务

负责AI对话记录的存储、查询、议价次数统计等功能
完全复刻原始 ai_reply_engine.py 中的对话管理逻辑
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from common.models.ai_chat_message import AIChatMessage


class AIConversationService:
    """AI对话服务
    
    负责：
    - 对话记录的保存和查询
    - 对话上下文获取
    - 议价次数统计
    - 最近消息查询（用于消息去重）
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def save_message(
        self,
        chat_id: str,
        cookie_id: str,
        user_id: str,
        item_id: str,
        role: str,
        content: str,
        intent: Optional[str] = None,
    ) -> Optional[datetime]:
        """保存对话记录
        
        Args:
            chat_id: 聊天ID
            cookie_id: 账号ID
            user_id: 用户ID
            item_id: 商品ID
            role: 角色（user/assistant）
            content: 内容
            intent: 意图（price/tech/default）
            
        Returns:
            创建时间或None
        """
        try:
            now = datetime.now(timezone.utc)
            message = AIChatMessage(
                chat_id=chat_id,
                cookie_id=cookie_id,
                user_id=user_id,
                item_id=item_id,
                role=role,
                content=content,
                intent=intent,
                created_at=now,
            )
            self.session.add(message)
            await self.session.commit()
            
            logger.debug(f"保存对话记录成功: chat_id={chat_id}, role={role}")
            return now
            
        except Exception as e:
            logger.error(f"保存对话记录失败: {e}")
            await self.session.rollback()
            return None
    
    async def get_context(
        self,
        chat_id: str,
        cookie_id: str,
        limit: int = 20,
    ) -> List[Dict[str, str]]:
        """获取对话上下文
        
        Args:
            chat_id: 聊天ID
            cookie_id: 账号ID
            limit: 最大记录数
            
        Returns:
            对话历史列表 [{"role": "user", "content": "..."}]
        """
        try:
            stmt = (
                select(AIChatMessage.role, AIChatMessage.content)
                .where(
                    AIChatMessage.chat_id == chat_id,
                    AIChatMessage.cookie_id == cookie_id,
                )
                .order_by(AIChatMessage.created_at.desc())
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            rows = result.all()
            
            # 反转顺序，使最早的消息在前
            context = [{"role": row[0], "content": row[1]} for row in reversed(rows)]
            return context
            
        except Exception as e:
            logger.error(f"获取对话上下文失败: {e}")
            return []
    
    async def get_bargain_count(
        self,
        chat_id: str,
        cookie_id: str,
    ) -> int:
        """获取议价次数
        
        统计该对话中意图为price且角色为user的消息数量
        
        Args:
            chat_id: 聊天ID
            cookie_id: 账号ID
            
        Returns:
            议价次数
        """
        try:
            stmt = (
                select(func.count())
                .select_from(AIChatMessage)
                .where(
                    AIChatMessage.chat_id == chat_id,
                    AIChatMessage.cookie_id == cookie_id,
                    AIChatMessage.intent == "price",
                    AIChatMessage.role == "user",
                )
            )
            result = await self.session.execute(stmt)
            count = result.scalar() or 0
            return count
            
        except Exception as e:
            logger.error(f"获取议价次数失败: {e}")
            return 0
    
    async def get_recent_user_messages(
        self,
        chat_id: str,
        cookie_id: str,
        seconds: int = 6,
    ) -> List[Dict[str, Any]]:
        """获取最近N秒内的用户消息
        
        用于消息去重，确保只处理最新的消息
        
        Args:
            chat_id: 聊天ID
            cookie_id: 账号ID
            seconds: 时间窗口（秒）
            
        Returns:
            消息列表 [{"content": "...", "created_at": datetime}]
        """
        try:
            # 计算时间阈值
            threshold = datetime.now(timezone.utc) - timedelta(seconds=seconds)
            
            stmt = (
                select(AIChatMessage.content, AIChatMessage.created_at)
                .where(
                    AIChatMessage.chat_id == chat_id,
                    AIChatMessage.cookie_id == cookie_id,
                    AIChatMessage.role == "user",
                    AIChatMessage.created_at >= threshold,
                )
                .order_by(AIChatMessage.created_at.asc())
            )
            result = await self.session.execute(stmt)
            rows = result.all()
            
            return [
                {"content": row[0], "created_at": row[1]}
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"获取最近用户消息失败: {e}")
            return []
    
    async def clear_conversation(
        self,
        chat_id: str,
        cookie_id: str,
    ) -> bool:
        """清空对话记录
        
        Args:
            chat_id: 聊天ID
            cookie_id: 账号ID
            
        Returns:
            是否成功
        """
        try:
            from sqlalchemy import delete
            
            stmt = delete(AIChatMessage).where(
                AIChatMessage.chat_id == chat_id,
                AIChatMessage.cookie_id == cookie_id,
            )
            await self.session.execute(stmt)
            await self.session.commit()
            
            logger.info(f"清空对话记录成功: chat_id={chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"清空对话记录失败: {e}")
            await self.session.rollback()
            return False
    
    async def get_conversation_stats(
        self,
        cookie_id: str,
        days: int = 7,
    ) -> Dict[str, Any]:
        """获取对话统计信息
        
        Args:
            cookie_id: 账号ID
            days: 统计天数
            
        Returns:
            统计信息字典
        """
        try:
            threshold = datetime.now(timezone.utc) - timedelta(days=days)
            
            # 总消息数
            total_stmt = (
                select(func.count())
                .select_from(AIChatMessage)
                .where(
                    AIChatMessage.cookie_id == cookie_id,
                    AIChatMessage.created_at >= threshold,
                )
            )
            total_result = await self.session.execute(total_stmt)
            total_count = total_result.scalar() or 0
            
            # 用户消息数
            user_stmt = (
                select(func.count())
                .select_from(AIChatMessage)
                .where(
                    AIChatMessage.cookie_id == cookie_id,
                    AIChatMessage.role == "user",
                    AIChatMessage.created_at >= threshold,
                )
            )
            user_result = await self.session.execute(user_stmt)
            user_count = user_result.scalar() or 0
            
            # AI回复数
            ai_stmt = (
                select(func.count())
                .select_from(AIChatMessage)
                .where(
                    AIChatMessage.cookie_id == cookie_id,
                    AIChatMessage.role == "assistant",
                    AIChatMessage.created_at >= threshold,
                )
            )
            ai_result = await self.session.execute(ai_stmt)
            ai_count = ai_result.scalar() or 0
            
            # 议价消息数
            bargain_stmt = (
                select(func.count())
                .select_from(AIChatMessage)
                .where(
                    AIChatMessage.cookie_id == cookie_id,
                    AIChatMessage.intent == "price",
                    AIChatMessage.created_at >= threshold,
                )
            )
            bargain_result = await self.session.execute(bargain_stmt)
            bargain_count = bargain_result.scalar() or 0
            
            return {
                "total_messages": total_count,
                "user_messages": user_count,
                "ai_replies": ai_count,
                "bargain_messages": bargain_count,
                "days": days,
            }
            
        except Exception as e:
            logger.error(f"获取对话统计失败: {e}")
            return {
                "total_messages": 0,
                "user_messages": 0,
                "ai_replies": 0,
                "bargain_messages": 0,
                "days": days,
            }
