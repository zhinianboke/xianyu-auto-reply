"""关键词匹配。由自动回复入口组合，保持现有调用签名。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.models.xy_keyword_rule import XYKeywordRule
from common.services.api_keyword_runtime import list_api_keyword_rules


class AutoReplyKeywordsMixin:
    """封装自动回复keywords相关处理。"""

    async def get_keyword_reply(
        self,
        session: AsyncSession,
        send_user_name: str,
        send_user_id: str,
        send_message: str,
        item_id: Optional[str] = None,
        chat_id: str = "",
    ) -> Optional[Any]:
        """获取关键词匹配回复
        
        支持:
        - 商品ID优先匹配
        - 图片、站外联系方式类型关键词
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
            try:
                keywords.extend(await list_api_keyword_rules(session, account.owner_id, account.id))
            except Exception:  # noqa: BLE001
                logger.exception("API关键词配置读取失败: account={}", self.cookie_id)
                if reply_trace is not None:
                    reply_trace["_api_keyword_error"] = "API关键词配置读取失败，请稍后重试"
                return "API关键词配置读取失败，请稍后重试"
            finally:
                if inspect(account).expired:
                    # 成功重试及最终失败中的rollback均会使缓存过期，下次重新加载。
                    self._account = None
            if not keywords:
                logger.info(f"账号 {self.cookie_id} 没有配置关键词")
                return None
            
            msg_lower = send_message.casefold()
            # The database order is only a storage order. Sort matching rules
            # explicitly so overlapping triggers do not depend on keyword text
            # or database collation.
            keywords = self._sort_keywords_for_message(keywords, msg_lower)
            
            if item_id:
                for kw in keywords:
                    keyword = kw.get("keyword", "")
                    keyword_lines = [line.strip() for line in keyword.splitlines() if line.strip()]
                    reply = kw.get("reply", "")
                    kw_item_id = kw.get("item_id", "")
                    kw_type = kw.get("type", "text")
                    image_url = kw.get("image_url", "")
                    matched_keyword = max(
                        (line for line in keyword_lines if line.casefold() in msg_lower),
                        key=len,
                        default="",
                    )
                    
                    if str(kw_item_id) == str(item_id) and matched_keyword:
                        logger.info(f"商品ID关键词匹配成功: 商品{item_id} '{matched_keyword}' (类型: {kw_type})")
                        if reply_trace is not None:
                            reply_trace["reply_strategy"] = "keyword"
                            reply_trace["matched_keyword"] = matched_keyword
                            reply_trace["matched_rule_type"] = "keyword_item"
                            reply_trace.setdefault("context_snapshot", {})["matched_item_title"] = kw.get("item_title") or None
                        
                        if kw_type == "image" and image_url:
                            image_reply = await self._handle_image_keyword(matched_keyword, image_url)
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

                        if kw_type == "external_contact":
                            external_reply = await self._do_external_contact_default_reply(
                                session=session,
                                settings=kw,
                                settings_item_id=None,
                                chat_id=chat_id,
                                send_user_id=send_user_id,
                                reply_trace=reply_trace,
                            )
                            if external_reply:
                                if reply_trace is not None:
                                    reply_trace["matched_rule_type"] = "keyword_item_external_contact"
                                return external_reply
                            return "EMPTY_REPLY"
                        
                        if not reply or not reply.strip():
                            logger.info(f"商品ID关键词 '{matched_keyword}' 回复内容为空,不进行回复")
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
                keyword_lines = [line.strip() for line in keyword.splitlines() if line.strip()]
                reply = kw.get("reply", "")
                kw_item_id = kw.get("item_id", "")
                kw_type = kw.get("type", "text")
                image_url = kw.get("image_url", "")
                matched_keyword = max(
                    (line for line in keyword_lines if line.casefold() in msg_lower),
                    key=len,
                    default="",
                )

                if not kw_item_id and matched_keyword:
                    logger.info(f"通用关键词匹配成功: '{matched_keyword}' (类型: {kw_type})")
                    if reply_trace is not None:
                        reply_trace["reply_strategy"] = "keyword"
                        reply_trace["matched_keyword"] = matched_keyword
                        reply_trace["matched_rule_type"] = "keyword_common"

                    if kw_type == "api_keyword":
                        if reply_trace is not None:
                            # 沿用通用关键词日志分类，API规则标识写入上下文。
                            reply_trace.setdefault("context_snapshot", {})["api_keyword_rule_id"] = kw["api_config"]["id"]
                        # 返回配置，聊天入口关闭查询会话后再执行HTTP请求及发货。
                        return {"_reply_mode": "api_keyword", "config": kw["api_config"]}

                    if kw_type == "image" and image_url:
                        image_reply = await self._handle_image_keyword(matched_keyword, image_url)
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

                    if kw_type == "external_contact":
                        external_reply = await self._do_external_contact_default_reply(
                            session=session,
                            settings=kw,
                            settings_item_id=None,
                            chat_id=chat_id,
                            send_user_id=send_user_id,
                            reply_trace=reply_trace,
                        )
                        if external_reply:
                            if reply_trace is not None:
                                reply_trace["matched_rule_type"] = "keyword_common_external_contact"
                            return external_reply
                        return "EMPTY_REPLY"

                    if not reply or not reply.strip():
                        logger.info(f"通用关键词 '{matched_keyword}' 回复内容为空,不进行回复")
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

            logger.info(f"未找到匹配的关键词: {send_message[:30]}...")
            return None

        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取关键词回复失败: {e}")
            return None

    async def _list_keywords(self, session: AsyncSession, account: XYAccount) -> list[dict]:
        """获取关键词列表（参照旧框架，添加is_active条件）"""
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
                    "type": rule_type,
                    "image_url": rule.image_url or "",
                    "item_title": item_title or "",
                    "location_name": rule.location_name or "",
                    "location_longitude": rule.location_longitude or "",
                    "location_latitude": rule.location_latitude or "",
                    "location_title": rule.location_title or "",
                    "location_subtitle": rule.location_subtitle or "",
                }
            )
        return keywords

    @classmethod
    def _sort_keywords_for_message(cls, keywords: list[dict], message_folded: str) -> list[dict]:
        """Sort rules by explicit reply priority for one incoming message.

        Item-specific rules remain ahead of common rules because
        ``get_keyword_reply`` evaluates those scopes in separate loops. Within
        either scope, images win over external-contact replies, then API and
        text. A longer matching line is more specific and wins within the same
        reply type. The original list index is the deterministic final tie
        breaker.
        """
        ranked: list[tuple[int, int, int, dict]] = []
        for index, keyword_rule in enumerate(keywords):
            lines = [
                line.strip()
                for line in str(keyword_rule.get("keyword") or "").splitlines()
                if line.strip()
            ]
            matching_lengths = [
                len(line)
                for line in lines
                if line.casefold() in message_folded
            ]
            match_length = max(matching_lengths, default=0)
            reply_type = str(keyword_rule.get("type") or "text").casefold()
            type_priority = cls.KEYWORD_REPLY_TYPE_PRIORITY.get(reply_type, 10)
            ranked.append((
                -type_priority if match_length else 0,
                -match_length if match_length else 0,
                index,
                keyword_rule,
            ))
        ranked.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
        return [entry[3] for entry in ranked]

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
