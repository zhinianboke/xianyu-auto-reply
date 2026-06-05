"""
AI回复引擎模块

负责AI对话生成、意图识别、议价处理
支持OpenAI兼容API、DashScope、Gemini等多种AI服务

功能：
1. 意图检测（基于关键词的本地检测）
2. AI回复生成（支持OpenAI/DashScope/Gemini）
3. 对话上下文管理
4. 议价次数控制
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.xy_account import XYAccount
from common.models.ai_chat_message import AIChatMessage
from common.services.ai_provider_service import (
    DEFAULT_AI_BASE_URL,
    build_anthropic_url,
    build_gemini_url,
    clean_ai_text,
    get_ai_settings_missing_fields,
    get_ai_provider_name,
    normalize_ai_provider_type,
    normalize_openai_base_url,
    read_ai_enabled,
)


class AIReplyEngine:
    """AI回复引擎
    
    负责：
    - 意图检测（本地关键词）
    - AI回复生成（支持OpenAI/DashScope/Gemini）
    - 对话上下文管理
    - 议价次数控制
    """
    
    _instance: Optional["AIReplyEngine"] = None
    
    def __init__(self):
        """初始化AI回复引擎"""
        self._init_default_prompts()
        self._chat_locks: Dict[str, asyncio.Lock] = {}
        self._chat_locks_usage_time: Dict[str, float] = {}  # 锁使用时间记录
        self._chat_locks_lock = asyncio.Lock()
        self._chat_locks_max_size = 10000  # 最大锁数量
        self._chat_locks_expire_time = 7200  # 锁过期时间（2小时）
        logger.info("AI回复引擎初始化完成")
    
    @classmethod
    def get_instance(cls) -> "AIReplyEngine":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = AIReplyEngine()
        return cls._instance
    
    def _init_default_prompts(self):
        """初始化默认提示词"""
        self.default_prompts = {
            "price": """你是一位经验丰富的销售专家，擅长议价。
语言要求：简短直接，每句≤10字，总字数≤40字。
议价策略：
1. 根据议价次数递减优惠：第1次小幅优惠，第2次中等优惠，第3次最大优惠
2. 接近最大议价轮数时要坚持底线，强调商品价值
3. 优惠不能超过设定的最大百分比和金额
4. 语气要友好但坚定，突出商品优势
注意：结合商品信息、对话历史和议价设置，给出合适的回复。""",
            
            "tech": """你是一位技术专家，专业解答产品相关问题。
语言要求：简短专业，每句≤10字，总字数≤40字。
回答重点：产品功能、使用方法、注意事项。
注意：基于商品信息回答，避免过度承诺。""",
            
            "default": """你是一位资深电商卖家，提供优质客服。
语言要求：简短友好，每句≤10字，总字数≤40字。
回答重点：商品介绍、物流、售后等常见问题。
注意：结合商品信息，给出实用建议。"""
        }
    
    def _normalize_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                if isinstance(item, str):
                    if item:
                        parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                else:
                    text = getattr(item, "text", None)
                if text is not None:
                    parts.append(str(text))
            return "".join(parts).strip()
        return str(value).strip()

    def _shorten_text(self, value: Any, limit: int = 800) -> str:
        text = self._normalize_text(value)
        if len(text) <= limit:
            return text
        return f"{text[:limit]}..."

    def _extract_readable_item_desc(self, value: Any) -> str:
        text = self._normalize_text(value)
        if not text:
            return "暂无商品描述"

        parsed: Any = None
        if isinstance(value, dict):
            parsed = value
        elif text.startswith("{") or text.startswith("["):
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None

        if isinstance(parsed, dict):
            for key in ("description", "desc", "item_description", "itemDesc", "content"):
                desc = self._normalize_text(parsed.get(key))
                if desc and not desc.startswith("{") and not desc.startswith("["):
                    return self._shorten_text(desc)

            detail_params = parsed.get("detail_params")
            if isinstance(detail_params, dict):
                parts = [
                    self._normalize_text(detail_params.get("title")),
                    self._normalize_text(detail_params.get("postInfo")),
                ]
            else:
                parts = [self._normalize_text(parsed.get("title"))]

            readable = "，".join(part for part in parts if part)
            return self._shorten_text(readable) if readable else "暂无商品描述"

        if text.startswith("{") or text.startswith("["):
            return "暂无商品描述"

        return self._shorten_text(text)

    def _build_openai_messages(self, messages: List[Dict]) -> List[Dict]:
        patched_messages = []
        direct_rule = "重要：只输出给买家的最终回复文本，不要输出思考过程、分析过程或解释，回复控制在40字以内。"
        has_system = False
        for msg in messages:
            if msg.get("role") == "system" and not has_system:
                has_system = True
                content = self._normalize_text(msg.get("content"))
                patched_messages.append({**msg, "content": f"{content}\n{direct_rule}" if content else direct_rule})
            else:
                patched_messages.append(msg)
        if not has_system:
            patched_messages.insert(0, {"role": "system", "content": direct_rule})
        return patched_messages

    def _convert_messages_to_text_parts(self, messages: List[Dict]) -> List[Dict]:
        converted_messages = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                converted_messages.append({**msg, "content": [{"type": "text", "text": content}]})
            else:
                converted_messages.append(msg)
        return converted_messages

    async def _create_openai_completion(
        self,
        client: Any,
        settings: Dict,
        messages: List[Dict],
        max_tokens: int,
        temperature: float,
        disable_thinking: bool,
    ) -> Any:
        kwargs: Dict[str, Any] = {
            "model": settings["model_name"],
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if disable_thinking:
            kwargs["extra_body"] = {"enable_thinking": False}
        return await client.chat.completions.create(**kwargs)

    async def _create_openai_completion_with_fallbacks(
        self,
        client: Any,
        settings: Dict,
        messages: List[Dict],
        max_tokens: int,
        temperature: float,
    ) -> Any:
        from openai import BadRequestError

        text_part_messages = self._convert_messages_to_text_parts(messages)
        attempts = [
            ("字符串content+禁用思考", messages, True),
            ("字符串content", messages, False),
            ("数组content+禁用思考", text_part_messages, True),
            ("数组content", text_part_messages, False),
        ]
        last_error: Optional[BadRequestError] = None
        for label, attempt_messages, disable_thinking in attempts:
            try:
                return await self._create_openai_completion(
                    client=client,
                    settings=settings,
                    messages=attempt_messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    disable_thinking=disable_thinking,
                )
            except BadRequestError as exc:
                last_error = exc
                logger.info(f"OpenAI API请求方式被拒绝，尝试下一种方式: {label}, model={settings.get('model_name')}: {exc}")
        if last_error:
            raise last_error
        raise RuntimeError("OpenAI API请求失败")

    async def _get_chat_lock(self, chat_id: str) -> asyncio.Lock:
        """获取指定chat_id的锁"""
        async with self._chat_locks_lock:
            current_time = time.time()
            
            # 定期清理过期的锁（当锁数量超过阈值时）
            if len(self._chat_locks) > self._chat_locks_max_size:
                await self._cleanup_expired_chat_locks(current_time)
            
            if chat_id not in self._chat_locks:
                self._chat_locks[chat_id] = asyncio.Lock()
            
            # 更新使用时间
            self._chat_locks_usage_time[chat_id] = current_time
            return self._chat_locks[chat_id]
    
    async def _cleanup_expired_chat_locks(self, current_time: float = None):
        """清理过期的聊天锁（防止内存泄漏）"""
        if current_time is None:
            current_time = time.time()
        
        expired_keys = [
            chat_id for chat_id, usage_time in self._chat_locks_usage_time.items()
            if current_time - usage_time > self._chat_locks_expire_time
        ]
        
        for chat_id in expired_keys:
            # 只清理未被持有的锁
            lock = self._chat_locks.get(chat_id)
            if lock and not lock.locked():
                self._chat_locks.pop(chat_id, None)
                self._chat_locks_usage_time.pop(chat_id, None)
        
        if expired_keys:
            logger.debug(f"AI回复引擎清理了 {len(expired_keys)} 个过期聊天锁")
    
    async def cleanup_chat_locks(self):
        """公开的清理方法，可在外部定期调用"""
        async with self._chat_locks_lock:
            await self._cleanup_expired_chat_locks()
    
    def detect_intent(self, message: str, cookie_id: str) -> str:
        """检测用户消息意图（基于关键词的本地检测）
        
        Args:
            message: 用户消息
            cookie_id: 账号ID
            
        Returns:
            意图类型: price/tech/default
        """
        try:
            msg_lower = message.lower()
            
            # 价格相关关键词
            price_keywords = [
                "便宜", "优惠", "刀", "降价", "价格", "多少钱",
                "能少", "还能", "最低", "底价", "实诚价", "到100", "能到",
                "包个邮"
            ]
            if any(kw in msg_lower for kw in price_keywords):
                logger.debug(f"【{cookie_id}】本地意图检测: price ({message[:20]}...)")
                return "price"
            
            # 技术相关关键词
            tech_keywords = [
                "怎么用", "参数", "坏了", "故障", "设置", "说明书",
                "功能", "用法", "教程", "驱动"
            ]
            if any(kw in msg_lower for kw in tech_keywords):
                logger.debug(f"【{cookie_id}】本地意图检测: tech ({message[:20]}...)")
                return "tech"
            
            logger.debug(f"【{cookie_id}】本地意图检测: default ({message[:20]}...)")
            return "default"
            
        except Exception as e:
            logger.error(f"【{cookie_id}】本地意图检测失败: {e}")
            return "default"
    
    async def _get_account(self, cookie_id: str, db_session: AsyncSession) -> Optional[XYAccount]:
        """获取账号信息"""
        stmt = select(XYAccount).where(XYAccount.account_id == cookie_id)
        result = await db_session.execute(stmt)
        return result.scalars().first()
    
    def _is_time_in_range(self, start_str: str, end_str: str) -> bool:
        """判断当前北京时间是否在指定范围内"""
        if not start_str or not end_str:
            return True
        try:
            from datetime import datetime, timezone, timedelta, time
            # 获取当前北京时间
            tz_bj = timezone(timedelta(hours=8))
            now_bj = datetime.now(tz_bj)
            current_time = now_bj.time()

            # 解析开始和结束时间
            def parse_time_str(t_str: str) -> time:
                parts = [int(p) for p in t_str.split(":")]
                if len(parts) == 2:
                    return time(parts[0], parts[1])
                elif len(parts) >= 3:
                    return time(parts[0], parts[1], parts[2])
                raise ValueError(f"Invalid time format: {t_str}")

            start_time = parse_time_str(start_str)
            end_time = parse_time_str(end_str)

            if start_time <= end_time:
                return start_time <= current_time <= end_time
            else:
                # 跨天情况 (例如 22:00 到 06:00)
                return current_time >= start_time or current_time <= end_time
        except Exception as e:
            logger.error(f"时间范围解析判断失败: {start_str} - {end_str}, error: {e}")
            return True

    async def is_ai_enabled(self, cookie_id: str, db_session: AsyncSession) -> bool:
        """检查指定账号是否启用AI回复（同时检查API Key是否配置及时间范围）"""
        try:
            account = await self._get_account(cookie_id, db_session)
            if not account:
                return False
            
            # 从账号的 metadata_json 中获取AI设置
            ai_settings = (account.metadata_json or {}).get("ai_reply_settings") or {}
            
            # 检查AI是否启用（兼容历史 enabled 字段）
            settings = self._extract_ai_settings(ai_settings)
            if not settings.get("ai_enabled"):
                return False
            
            missing_fields = get_ai_settings_missing_fields(settings)
            if missing_fields:
                logger.warning(f"【{cookie_id}】AI已启用但配置未填写完整，跳过AI回复: {'、'.join(missing_fields)}")
                return False
            
            # 检查启用时间范围
            start_str = settings.get("ai_time_range_start", "")
            end_str = settings.get("ai_time_range_end", "")
            if not self._is_time_in_range(start_str, end_str):
                logger.info(f"【{cookie_id}】当前时间不在AI启用时间段（{start_str} - {end_str}）内，跳过AI回复")
                return False
            
            return True
        except Exception as e:
            logger.error(f"【{cookie_id}】检查AI启用状态失败: {e}")
            return False
    
    async def get_ai_settings(self, cookie_id: str, db_session: AsyncSession) -> Dict[str, Any]:
        """获取AI回复设置"""
        try:
            account = await self._get_account(cookie_id, db_session)
            if not account:
                return self._get_default_settings()
            
            # 从账号的 metadata_json 中获取AI设置
            ai_settings = (account.metadata_json or {}).get("ai_reply_settings") or {}
            
            if not ai_settings:
                return self._get_default_settings()
            
            return self._extract_ai_settings(ai_settings)
        except Exception as e:
            logger.error(f"【{cookie_id}】获取AI设置失败: {e}")
            return self._get_default_settings()
    
    def _get_default_settings(self) -> Dict[str, Any]:
        """获取默认AI设置"""
        return {
            "ai_enabled": False,
            "provider_type": "openai_compatible",
            "api_key": "",
            "base_url": DEFAULT_AI_BASE_URL,
            "model_name": "qwen-plus",
            "max_bargain_rounds": 3,
            "max_discount_percent": 10,
            "max_discount_amount": 100,
            "custom_prompts": "",
            "ai_time_range_start": "",
            "ai_time_range_end": "",
        }

    def _extract_ai_settings(self, ai_settings: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._get_default_settings()
        payload.update({k: v for k, v in (ai_settings or {}).items() if v is not None})
        payload["ai_enabled"] = read_ai_enabled(ai_settings)
        payload["provider_type"] = normalize_ai_provider_type(
            payload.get("provider_type"),
            payload.get("base_url"),
            payload.get("model_name"),
        )
        payload["api_key"] = clean_ai_text(payload.get("api_key"))
        payload["base_url"] = clean_ai_text(payload.get("base_url"))
        payload["model_name"] = clean_ai_text(payload.get("model_name"))
        payload["max_bargain_rounds"] = int(payload.get("max_bargain_rounds") or 3)
        payload["max_discount_percent"] = int(payload.get("max_discount_percent") or 10)
        payload["max_discount_amount"] = int(payload.get("max_discount_amount") or 100)
        payload["custom_prompts"] = payload.get("custom_prompts") or ""
        payload["ai_time_range_start"] = payload.get("ai_time_range_start") or ""
        payload["ai_time_range_end"] = payload.get("ai_time_range_end") or ""
        return payload
    
    def _get_api_provider_name(self, settings: Dict) -> str:
        """识别AI服务商名称（用于日志显示）"""
        return get_ai_provider_name(
            settings.get("provider_type"),
            settings.get("base_url"),
            settings.get("model_name"),
        )

    async def _call_openai_api(
        self,
        settings: Dict,
        messages: List[Dict],
        max_tokens: int = 8192,
        temperature: float = 0.5,
    ) -> str:
        """调用OpenAI兼容API"""
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(
                api_key=settings["api_key"],
                base_url=normalize_openai_base_url(settings["base_url"]),
            )
            
            request_messages = self._build_openai_messages(messages)
            response = await self._create_openai_completion_with_fallbacks(
                client=client,
                settings=settings,
                messages=request_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            choice = response.choices[0]
            message = choice.message
            reply_text = self._normalize_text(message.content)
            if not reply_text:
                message_keys = []
                try:
                    message_data = message.model_dump()
                    message_keys = [key for key, val in message_data.items() if val]
                except Exception:
                    message_keys = []
                logger.warning(
                    f"OpenAI API返回空内容: finish_reason={getattr(choice, 'finish_reason', None)}, message字段={message_keys}"
                )
                if getattr(choice, "finish_reason", None) == "length":
                    retry_max_tokens = max(max_tokens * 2, 1024)
                    logger.warning(
                        f"OpenAI API输出被截断，使用 max_tokens={retry_max_tokens} 重试一次"
                    )
                    retry_response = await self._create_openai_completion_with_fallbacks(
                        client=client,
                        settings=settings,
                        messages=request_messages,
                        max_tokens=retry_max_tokens,
                        temperature=temperature,
                    )
                    retry_choice = retry_response.choices[0]
                    retry_message = retry_choice.message
                    reply_text = self._normalize_text(retry_message.content)
                    if not reply_text:
                        retry_keys = []
                        try:
                            retry_data = retry_message.model_dump()
                            retry_keys = [key for key, val in retry_data.items() if val]
                        except Exception:
                            retry_keys = []
                        logger.warning(
                            f"OpenAI API重试后仍返回空内容: finish_reason={getattr(retry_choice, 'finish_reason', None)}, message字段={retry_keys}"
                        )
            return reply_text
            
        except Exception as e:
            logger.error(f"OpenAI API调用失败: {e}")
            raise
    
    async def _call_dashscope_api(
        self,
        settings: Dict,
        messages: List[Dict],
        max_tokens: int = 100,
        temperature: float = 0.7,
    ) -> str:
        """调用DashScope API"""
        try:
            base_url = settings["base_url"]
            if "/apps/" in base_url:
                app_id = base_url.split("/apps/")[-1].split("/")[0]
            else:
                raise ValueError("DashScope API URL中未找到app_id")
            
            url = f"https://dashscope.aliyuncs.com/api/v1/apps/{app_id}/completion"
            
            system_content = ""
            user_content = ""
            for msg in messages:
                if msg["role"] == "system":
                    system_content = msg["content"]
                elif msg["role"] == "user":
                    user_content = msg["content"]
            
            if system_content and user_content:
                prompt = f"{system_content}\n\n用户问题：{user_content}\n\n请直接回答用户的问题："
            elif user_content:
                prompt = user_content
            else:
                prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
            
            data = {
                "input": {"prompt": prompt},
                "parameters": {"max_tokens": max_tokens, "temperature": temperature},
                "debug": {},
            }
            headers = {
                "Authorization": f"Bearer {settings['api_key']}",
                "Content-Type": "application/json",
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers=headers, json=data)
                response.raise_for_status()
                result = response.json()
            
            if "output" in result and "text" in result["output"]:
                reply_text = self._normalize_text(result["output"]["text"])
                if not reply_text:
                    logger.warning("DashScope API返回空内容")
                return reply_text
            else:
                raise Exception(f"DashScope API响应格式错误: {result}")
                
        except Exception as e:
            logger.error(f"DashScope API调用失败: {e}")
            raise
    
    async def _call_gemini_api(
        self,
        settings: Dict,
        messages: List[Dict],
        max_tokens: int = 100,
        temperature: float = 0.7,
    ) -> str:
        """调用Gemini API"""
        try:
            api_key = settings["api_key"]
            model_name = settings["model_name"]
            base_url = settings.get("base_url", "")
            
            url = build_gemini_url(base_url, f"/models/{model_name}:generateContent")
            
            system_instruction = ""
            user_content_parts = []
            
            for msg in messages:
                if msg["role"] == "system":
                    system_instruction = msg["content"]
                elif msg["role"] == "user":
                    user_content_parts.append(msg["content"])
            
            user_content = "\n".join(user_content_parts)
            
            if not user_content:
                raise ValueError("未在消息中找到用户内容")
            
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": user_content}],
                    }
                ],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            }
            
            if system_instruction:
                payload["systemInstruction"] = {
                    "parts": [{"text": system_instruction}]
                }
            
            headers = {"Content-Type": "application/json"}
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers=headers, params={"key": api_key}, json=payload)
                response.raise_for_status()
                result = response.json()
            
            reply_text = result["candidates"][0]["content"]["parts"][0]["text"]
            normalized_reply = self._normalize_text(reply_text)
            if not normalized_reply:
                logger.warning("Gemini API返回空内容")
            return normalized_reply
            
        except Exception as e:
            logger.error(f"Gemini API调用失败: {e}")
            raise
    
    async def _call_anthropic_api(
        self,
        settings: Dict,
        messages: List[Dict],
        max_tokens: int = 100,
        temperature: float = 0.7,
    ) -> str:
        """调用Anthropic Claude官方API"""
        try:
            api_key = settings["api_key"]
            model_name = settings["model_name"]
            base_url = settings.get("base_url", "")
            
            url = build_anthropic_url(base_url, "/messages")
            
            system_content = ""
            user_messages: List[Dict[str, Any]] = []
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "system":
                    system_content = content
                elif role in ("user", "assistant"):
                    user_messages.append({"role": role, "content": content})
            
            payload: Dict[str, Any] = {
                "model": model_name,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": user_messages or [{"role": "user", "content": ""}],
            }
            if system_content:
                payload["system"] = system_content
            
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
            
            content_parts = result.get("content", []) if isinstance(result, dict) else []
            for item in content_parts:
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                    reply_text = self._normalize_text(item["text"])
                    if not reply_text:
                        logger.warning("Anthropic API返回空内容")
                    return reply_text
            raise RuntimeError(f"Anthropic API响应格式错误: {result}")
            
        except Exception as e:
            logger.error(f"Anthropic API调用失败: {e}")
            raise

    async def generate_reply(
        self,
        message: str,
        item_info: Dict[str, Any],
        chat_id: str,
        cookie_id: str,
        user_id: str,
        item_id: str,
        db_session: AsyncSession,
        skip_wait: bool = False,
    ) -> Optional[str]:
        """生成AI回复
        
        Args:
            message: 用户消息
            item_info: 商品信息
            chat_id: 聊天ID
            cookie_id: 账号ID
            user_id: 用户ID
            item_id: 商品ID
            db_session: 数据库会话
            skip_wait: 是否跳过等待（默认False）
            
        Returns:
            AI回复或None
        """
        try:
            # 检查AI是否启用
            if not await self.is_ai_enabled(cookie_id, db_session):
                return None
            
            # 检测意图
            intent = self.detect_intent(message, cookie_id)
            logger.info(f"【{cookie_id}】检测到意图: {intent}")
            
            # 保存用户消息到数据库
            now = datetime.now(timezone.utc)
            user_message = AIChatMessage(
                chat_id=chat_id,
                cookie_id=cookie_id,
                user_id=user_id,
                item_id=item_id,
                role="user",
                content=message,
                intent=intent,
                created_at=now,
            )
            db_session.add(user_message)
            await db_session.commit()
            message_created_at = now
            
            # 等待收集后续消息（如果未跳过）
            if not skip_wait:
                logger.info(f"【{cookie_id}】消息已保存，等待3秒收集后续消息")
                await asyncio.sleep(3)
            
            # 获取chat锁，确保同一对话串行处理
            chat_lock = await self._get_chat_lock(chat_id)
            
            async with chat_lock:
                # 获取最近消息，检查是否有更新的消息
                query_seconds = 6 if skip_wait else 25
                threshold = datetime.now(timezone.utc) - timedelta(seconds=query_seconds)
                
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
                result = await db_session.execute(stmt)
                recent_messages = result.all()
                
                if recent_messages and len(recent_messages) > 0:
                    latest_message = recent_messages[-1]
                    logger.debug(f"【{cookie_id}】当前消息时间: {message_created_at}, 最新消息时间: {latest_message[1]}, 最新消息内容: {latest_message[0][:20]}")
                    # 只有当最新消息的内容与当前消息不同时才跳过
                    if message_created_at and latest_message[1] != message_created_at and latest_message[0] != message:
                        logger.info(f"【{cookie_id}】检测到有更新的消息，跳过当前消息")
                        return None
                
                # 获取AI设置
                settings = await self.get_ai_settings(cookie_id, db_session)
                if not settings.get("ai_enabled"):
                    return None
                
                # 获取对话历史
                context_stmt = (
                    select(AIChatMessage.role, AIChatMessage.content)
                    .where(
                        AIChatMessage.chat_id == chat_id,
                        AIChatMessage.cookie_id == cookie_id,
                    )
                    .order_by(AIChatMessage.created_at.desc())
                    .limit(20)
                )
                context_result = await db_session.execute(context_stmt)
                context_rows = context_result.all()
                context = [{"role": row[0], "content": row[1]} for row in reversed(context_rows)]
                
                # 获取议价次数
                from sqlalchemy import func
                bargain_stmt = (
                    select(func.count())
                    .select_from(AIChatMessage)
                    .where(
                        AIChatMessage.chat_id == chat_id,
                        AIChatMessage.cookie_id == cookie_id,
                        AIChatMessage.intent == "price",
                        AIChatMessage.role == "user",
                    )
                )
                bargain_result = await db_session.execute(bargain_stmt)
                bargain_count = bargain_result.scalar() or 0
                
                # 检查议价轮数限制
                if intent == "price":
                    max_bargain_rounds = settings.get("max_bargain_rounds", 3)
                    if bargain_count >= max_bargain_rounds:
                        logger.info(f"【{cookie_id}】议价次数已达上限 ({bargain_count}/{max_bargain_rounds})")
                        refuse_reply = "抱歉，这个价格已经是最优惠的了，不能再便宜了哦！"
                        
                        # 保存拒绝回复
                        refuse_message = AIChatMessage(
                            chat_id=chat_id,
                            cookie_id=cookie_id,
                            user_id=user_id,
                            item_id=item_id,
                            role="assistant",
                            content=refuse_reply,
                            intent=intent,
                            created_at=datetime.now(timezone.utc),
                        )
                        db_session.add(refuse_message)
                        await db_session.commit()
                        
                        return refuse_reply
                
                # 构建提示词
                custom_prompts = settings.get("custom_prompts", "")
                if isinstance(custom_prompts, str) and custom_prompts:
                    try:
                        custom_prompts = json.loads(custom_prompts)
                    except Exception:
                        custom_prompts = {}
                elif not isinstance(custom_prompts, dict):
                    custom_prompts = {}
                
                system_prompt = custom_prompts.get(
                    intent, self.default_prompts.get(intent, self.default_prompts["default"])
                )
                
                # 构建商品信息
                item_desc = f"商品标题: {self._shorten_text(item_info.get('title', '未知'), 120)}\n"
                item_desc += f"商品价格: {item_info.get('price', '未知')}元\n"
                item_desc += f"商品描述: {self._extract_readable_item_desc(item_info.get('desc'))}"
                
                # 添加商品AI提示词
                ai_prompt = item_info.get('ai_prompt', '')
                if ai_prompt:
                    item_desc += f"\n商品特殊说明: {self._shorten_text(ai_prompt)}"
                
                logger.info(f"[AI回复] 商品信息构建完成: {item_desc}")
                
                # 构建对话历史
                context_str = "\n".join([
                    f"{msg['role']}: {msg['content']}" for msg in context[-10:]
                ])
                
                # 构建用户消息
                max_bargain_rounds = settings.get("max_bargain_rounds", 3)
                max_discount_percent = settings.get("max_discount_percent", 10)
                max_discount_amount = settings.get("max_discount_amount", 100)
                
                user_prompt = f"""商品信息：
{item_desc}

对话历史：
{context_str}

议价设置：
- 当前议价次数：{bargain_count}
- 最大议价轮数：{max_bargain_rounds}
- 最大优惠百分比：{max_discount_percent}%
- 最大优惠金额：{max_discount_amount}元

用户消息：{message}

请根据以上信息生成回复："""
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                
                # 调用AI生成回复
                reply = None
                
                # 检查API Key是否配置（必须是非空字符串）
                api_key = (settings.get("api_key") or "").strip()
                if not api_key:
                    logger.warning(f"【{cookie_id}】API Key未配置，跳过AI调用")
                    return None
                
                # 识别AI服务商
                provider_name = self._get_api_provider_name(settings)
                logger.info(f"【{cookie_id}】AI设置: 服务商={provider_name}, model={settings.get('model_name')}, api_key长度={len(api_key)}")
                
                provider_type = normalize_ai_provider_type(
                    settings.get("provider_type"),
                    settings.get("base_url"),
                    settings.get("model_name"),
                )
                logger.info(f"【{cookie_id}】使用{provider_name} API生成回复 (provider_type={provider_type})")
                if provider_type == "dashscope_app":
                    reply = await self._call_dashscope_api(settings, messages)
                elif provider_type == "gemini":
                    reply = await self._call_gemini_api(settings, messages)
                elif provider_type == "anthropic":
                    reply = await self._call_anthropic_api(settings, messages)
                else:
                    reply = await self._call_openai_api(settings, messages)
                
                if reply:
                    # 保存AI回复（带重试机制，防止连接丢失）
                    await self._save_ai_message_with_retry(
                        cookie_id, chat_id, user_id, item_id, reply, intent
                    )
                    logger.info(f"【{cookie_id}】AI回复生成成功: {reply[:50]}...")
                
                return reply
                
        except Exception as e:
            logger.error(f"【{cookie_id}】AI回复生成失败: {type(e).__name__}: {e}")
            return None
    
    async def _save_ai_message_with_retry(
        self,
        cookie_id: str,
        chat_id: str,
        user_id: str,
        item_id: str,
        content: str,
        intent: str,
        max_retry: int = 3
    ) -> bool:
        """保存AI聊天消息（带重试机制）
        
        Args:
            cookie_id: Cookie ID
            chat_id: 会话ID
            user_id: 用户ID
            item_id: 商品ID
            content: 消息内容
            intent: 意图
            max_retry: 最大重试次数
        Returns:
            是否保存成功
        """
        for attempt in range(max_retry):
            try:
                async with async_session_maker() as db_session:
                    ai_message = AIChatMessage(
                        chat_id=chat_id,
                        cookie_id=cookie_id,
                        user_id=user_id,
                        item_id=item_id,
                        role="assistant",
                        content=content,
                        intent=intent,
                        created_at=datetime.now(timezone.utc),
                    )
                    db_session.add(ai_message)
                    await db_session.commit()
                    return True
            except Exception as e:
                if attempt < max_retry - 1:
                    logger.warning(f"【{cookie_id}】保存AI消息失败，重试({attempt + 1}/{max_retry}): {type(e).__name__}")
                    await asyncio.sleep(0.5)
                else:
                    logger.error(f"【{cookie_id}】保存AI消息最终失败: {type(e).__name__}: {e}")
        return False


# 全局AI回复引擎实例
_ai_reply_engine: Optional[AIReplyEngine] = None


def get_ai_reply_engine() -> AIReplyEngine:
    """获取全局AI回复引擎"""
    global _ai_reply_engine
    if _ai_reply_engine is None:
        _ai_reply_engine = AIReplyEngine.get_instance()
    return _ai_reply_engine
