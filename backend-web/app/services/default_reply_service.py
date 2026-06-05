"""默认回复服务"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.default_reply import DefaultReply, DefaultReplyRecord


class DefaultReplyService:
    """默认回复服务类"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_default_reply(self, account_id: str) -> Optional[Dict[str, Any]]:
        """获取账号的默认回复设置（账号级别，item_id为空）"""
        stmt = select(DefaultReply).where(
            DefaultReply.account_id == account_id,
            DefaultReply.item_id.is_(None)  # 账号级别默认回复，item_id为空
        )
        result = await self.session.execute(stmt)
        reply = result.scalars().first()
        if not reply:
            return None
        return {
            "enabled": reply.enabled,
            "reply_type": reply.reply_type or "text",
            "reply_content": reply.reply_content or "",
            "reply_image": reply.reply_image or "",
            "api_url": reply.api_url or "",
            "api_timeout": reply.api_timeout or 80,
            "reply_once": reply.reply_once,
        }

    async def save_default_reply(
        self,
        account_id: str,
        enabled: bool,
        reply_content: str,
        reply_once: bool = False,
        reply_image: str = "",
        reply_type: str = "text",
        api_url: str = "",
        api_timeout: int = 80,
    ) -> bool:
        """保存默认回复设置（账号级别，item_id为空）"""
        stmt = select(DefaultReply).where(
            DefaultReply.account_id == account_id,
            DefaultReply.item_id.is_(None)  # 账号级别默认回复，item_id为空
        )
        result = await self.session.execute(stmt)
        reply = result.scalars().first()

        if reply:
            reply.enabled = enabled
            reply.reply_type = reply_type
            reply.reply_content = reply_content
            reply.reply_image = reply_image
            reply.api_url = api_url
            reply.api_timeout = api_timeout
            reply.reply_once = reply_once
        else:
            reply = DefaultReply(
                account_id=account_id,
                item_id=None,  # 账号级别默认回复
                enabled=enabled,
                reply_type=reply_type,
                reply_content=reply_content,
                reply_image=reply_image,
                api_url=api_url,
                api_timeout=api_timeout,
                reply_once=reply_once,
            )
            self.session.add(reply)

        await self.session.commit()
        return True

    async def delete_default_reply(self, account_id: str) -> bool:
        """删除默认回复设置（账号级别，item_id为空）"""
        stmt = delete(DefaultReply).where(
            DefaultReply.account_id == account_id,
            DefaultReply.item_id.is_(None)  # 账号级别默认回复，item_id为空
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def get_all_default_replies(self, account_ids: list[str]) -> Dict[str, Dict[str, Any]]:
        """获取多个账号的默认回复设置（账号级别，item_id为空）"""
        stmt = select(DefaultReply).where(
            DefaultReply.account_id.in_(account_ids),
            DefaultReply.item_id.is_(None)  # 账号级别默认回复，item_id为空
        )
        result = await self.session.execute(stmt)
        replies = result.scalars().all()
        
        return {
            reply.account_id: {
                "enabled": reply.enabled,
                "reply_type": reply.reply_type or "text",
                "reply_content": reply.reply_content or "",
                "reply_image": reply.reply_image or "",
                "api_url": reply.api_url or "",
                "api_timeout": reply.api_timeout or 80,
                "reply_once": reply.reply_once,
            }
            for reply in replies
        }

    async def clear_reply_records(self, account_id: str) -> bool:
        """清空默认回复记录（账号级别，item_id为空）"""
        stmt = delete(DefaultReplyRecord).where(
            DefaultReplyRecord.account_id == account_id,
            DefaultReplyRecord.item_id.is_(None)  # 账号级别默认回复记录
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return True

    async def check_user_replied(self, account_id: str, user_id: str) -> bool:
        """检查是否已回复过该用户（账号级别，item_id为空）"""
        stmt = select(DefaultReplyRecord).where(
            DefaultReplyRecord.account_id == account_id,
            DefaultReplyRecord.item_id.is_(None),  # 账号级别默认回复记录
            DefaultReplyRecord.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None

    async def record_user_replied(self, account_id: str, user_id: str) -> None:
        """记录已回复用户（账号级别，item_id为空）"""
        record = DefaultReplyRecord(account_id=account_id, item_id=None, user_id=user_id)
        self.session.add(record)
        await self.session.commit()

    # ==================== 商品级别默认回复 ====================

    async def get_item_default_reply(self, account_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        """获取商品级别的默认回复设置"""
        if not item_id:
            return None
        
        stmt = select(DefaultReply).where(
            DefaultReply.account_id == account_id,
            DefaultReply.item_id == item_id
        )
        result = await self.session.execute(stmt)
        reply = result.scalars().first()
        if not reply:
            return None
        return {
            "enabled": reply.enabled,
            "reply_type": reply.reply_type or "text",
            "reply_content": reply.reply_content or "",
            "reply_image": reply.reply_image or "",
            "api_url": reply.api_url or "",
            "api_timeout": reply.api_timeout or 80,
            "reply_once": reply.reply_once,
            "item_id": reply.item_id,
        }

    async def save_item_default_reply(
        self,
        account_id: str,
        item_id: str,
        reply_content: str,
        enabled: bool = True,
        reply_once: bool = False,
        reply_image: str = "",
        reply_type: str = "text",
        api_url: str = "",
        api_timeout: int = 80,
    ) -> bool:
        """保存商品级别的默认回复设置"""
        stmt = select(DefaultReply).where(
            DefaultReply.account_id == account_id,
            DefaultReply.item_id == item_id
        )
        result = await self.session.execute(stmt)
        reply = result.scalars().first()

        if reply:
            reply.enabled = enabled
            reply.reply_type = reply_type
            reply.reply_content = reply_content
            reply.reply_image = reply_image
            reply.api_url = api_url
            reply.api_timeout = api_timeout
            reply.reply_once = reply_once
        else:
            reply = DefaultReply(
                account_id=account_id,
                item_id=item_id,
                enabled=enabled,
                reply_type=reply_type,
                reply_content=reply_content,
                reply_image=reply_image,
                api_url=api_url,
                api_timeout=api_timeout,
                reply_once=reply_once,
            )
            self.session.add(reply)

        await self.session.commit()
        return True

    async def delete_item_default_reply(self, account_id: str, item_id: str) -> bool:
        """删除商品级别的默认回复设置"""
        stmt = delete(DefaultReply).where(
            DefaultReply.account_id == account_id,
            DefaultReply.item_id == item_id
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def check_item_user_replied(self, account_id: str, item_id: str, user_id: str) -> bool:
        """检查是否已回复过该用户（商品级别）"""
        stmt = select(DefaultReplyRecord).where(
            DefaultReplyRecord.account_id == account_id,
            DefaultReplyRecord.item_id == item_id,
            DefaultReplyRecord.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None

    async def record_item_user_replied(self, account_id: str, item_id: str, user_id: str) -> None:
        """记录已回复用户（商品级别）"""
        record = DefaultReplyRecord(account_id=account_id, item_id=item_id, user_id=user_id)
        self.session.add(record)
        await self.session.commit()
