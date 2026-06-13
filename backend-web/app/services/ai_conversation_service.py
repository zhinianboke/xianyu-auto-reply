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


def _estimate_tokens(text: str) -> int:
    """估算文本的token数量
    
    优先使用tiktoken（如果已安装），否则使用简单的字符数估算。
    对于中文，大约1个汉字≈1-2个token；英文约4个字符≈1个token。
    这里使用保守估算：len(text) // 2 + 1
    
    Args:
        text: 输入文本
        
    Returns:
        估算的token数
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        # tiktoken未安装，使用字符数估算
        return len(text) // 2 + 1
    except Exception:
        logger.debug("AIConversationService: tiktoken unavailable, using char-based estimation")
        return len(text) // 2 + 1


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
        self._summary_cache: Dict[str, tuple] = {}  # {cache_key: (summary_text, timestamp)}
    
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
    
    async def get_context_with_token_limit(
        self,
        chat_id: str,
        cookie_id: str,
        limit: int = 20,
        max_tokens: int = 2000,
    ) -> List[Dict[str, str]]:
        """获取对话上下文（带token限制）
        
        从数据库获取对话历史，并确保总token数不超过max_tokens。
        从最旧的消息开始截断，保留最新的对话内容。
        
        Args:
            chat_id: 聊天ID
            cookie_id: 账号ID
            limit: 最大记录数
            max_tokens: 最大token数（默认2000）
            
        Returns:
            对话历史列表 [{"role": "user", "content": "..."}]
        """
        try:
            # 先获取原始上下文
            context = await self.get_context(chat_id, cookie_id, limit)
            
            if not context:
                return []
            
            # 从最新消息开始计算token，保留尽可能多的近期消息
            total_tokens = 0
            selected_start = len(context)
            
            # 从后往前（最新到最旧）累加token
            for i in range(len(context) - 1, -1, -1):
                msg_tokens = _estimate_tokens(context[i]["content"])
                if total_tokens + msg_tokens > max_tokens:
                    # 超出限制，从此处截断（保留i+1之后的消息）
                    selected_start = i + 1
                    break
                total_tokens += msg_tokens
            
            truncated = context[selected_start:]
            
            if len(truncated) < len(context):
                logger.info(
                    f"对话上下文token截断: {len(context)} -> {len(truncated)} 条消息, "
                    f"估算token: ~{total_tokens}/{max_tokens}"
                )
            
            return truncated
            
        except Exception as e:
            logger.error(f"获取token限制上下文失败: {e}")
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
    
    async def generate_summary(
        self,
        chat_id: str,
        cookie_id: str,
        max_length: int = 200,
    ) -> Optional[str]:
        """生成对话摘要

        加载完整对话历史，使用AI模型生成简洁摘要。
        摘要会缓存30分钟。

        Args:
            chat_id: 聊天ID
            cookie_id: 账号ID
            max_length: 摘要最大字符数

        Returns:
            摘要文本，失败返回None
        """
        try:
            # 检查缓存
            cache_key = f"summary:{chat_id}:{cookie_id}"
            cached = self._summary_cache.get(cache_key)
            if cached:
                cached_text, cached_time = cached
                if (datetime.now(timezone.utc) - cached_time).total_seconds() < 1800:
                    logger.debug(f"对话摘要缓存命中: chat_id={chat_id}")
                    return cached_text

            # 获取对话历史（不限制条数，获取全部）
            context = await self.get_context(chat_id, cookie_id, limit=100)
            if not context:
                return None

            # 构建对话文本
            conversation_text = "\n".join(
                f"{'用户' if msg['role'] == 'user' else 'AI'}: {msg['content']}"
                for msg in context
            )

            # 截断过长的对话
            if len(conversation_text) > 3000:
                conversation_text = conversation_text[-3000:]

            # 构建摘要请求
            summary_prompt = f"""请为以下对话生成一个简洁的摘要（不超过{max_length}字），
包含：对话主题、用户主要需求、当前状态（是否已成交/议价中/咨询中）。

对话内容：
{conversation_text}"""

            # 调用AI模型生成摘要
            summary = await self._call_ai_for_summary(summary_prompt, max_length)
            if summary:
                # 缓存结果
                self._summary_cache[cache_key] = (summary, datetime.now(timezone.utc))
                logger.info(f"生成对话摘要成功: chat_id={chat_id}, 长度={len(summary)}")
                return summary

            return None

        except Exception as e:
            logger.error(f"生成对话摘要失败: {e}")
            return None

    async def _call_ai_for_summary(self, prompt: str, max_length: int) -> Optional[str]:
        """调用AI模型生成摘要

        Args:
            prompt: 摘要请求提示词
            max_length: 最大字符数

        Returns:
            摘要文本
        """
        try:
            import httpx
            from common.services.ai_client_pool import get_ai_client_pool
            from common.models.xy_account import XYAccount
            from sqlalchemy import select

            # 获取AI配置（使用第一个可用账号的配置）
            stmt = select(XYAccount).where(
                XYAccount.ai_enabled == True,
                XYAccount.ai_base_url.isnot(None),
                XYAccount.ai_api_key.isnot(None),
            ).limit(1)
            result = await self.session.execute(stmt)
            account = result.scalar_one_or_none()

            if not account:
                logger.warning("未找到AI配置，无法生成摘要")
                return None

            # 使用AI客户端池
            client_pool = get_ai_client_pool()
            client = await client_pool.get_client(
                provider_type='openai_compatible',
                base_url=account.ai_base_url,
                api_key=account.ai_api_key,
            )

            # 调用AI API
            response = await client.chat.completions.create(
                model=account.ai_model_name or "gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "你是一个对话摘要助手，负责生成简洁的对话摘要。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3,
            )

            if response.choices and response.choices[0].message:
                summary = response.choices[0].message.content.strip()
                # 确保不超过最大长度
                if len(summary) > max_length:
                    summary = summary[:max_length-3] + "..."
                return summary

            return None

        except Exception as e:
            logger.error(f"调用AI生成摘要失败: {e}")
            return None

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
