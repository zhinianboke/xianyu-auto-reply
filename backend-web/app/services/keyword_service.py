"""
关键词服务

功能：
1. 关键词规则CRUD操作
2. 支持文本和图片关键词
3. 关键词冲突检测
4. 批量替换文本关键词
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.models.xy_keyword_rule import XYKeywordRule


class KeywordService:
    """Business logic for keyword CRUD compatible with the legacy API."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_keywords_for_owner(self, owner_id: int | None = None) -> list[dict]:
        stmt = (
            select(XYKeywordRule, XYCatalogItem.title, XYAccount.account_id)
            .join(XYAccount, XYAccount.id == XYKeywordRule.account_pk)
            .outerjoin(
                XYCatalogItem,
                (XYCatalogItem.account_pk == XYKeywordRule.account_pk)
                & (XYCatalogItem.item_id == XYKeywordRule.item_id),
            )
            .order_by(XYAccount.account_id, XYKeywordRule.keyword, XYKeywordRule.item_id)
        )
        if owner_id is not None:
            stmt = stmt.where(XYKeywordRule.owner_id == owner_id)

        rows = await self.session.execute(stmt)
        keywords: list[dict] = []
        for rule, item_title, account_id in rows.all():
            rule_type = (rule.reply_type or "text").lower()
            keywords.append(
                {
                    "keyword": rule.keyword,
                    "reply": rule.reply_content or "",
                    "item_id": rule.item_id or "",
                    "type": "image" if rule_type == "image" else "text",
                    "image_url": rule.image_url or "",
                    "item_title": item_title or "",
                    "account_id": account_id or "",
                }
            )
        return keywords

    async def list_keywords(self, account: XYAccount) -> list[dict]:
        stmt = (
            select(XYKeywordRule, XYCatalogItem.title)
            .outerjoin(
                XYCatalogItem,
                (XYCatalogItem.account_pk == XYKeywordRule.account_pk)
                & (XYCatalogItem.item_id == XYKeywordRule.item_id),
            )
            .where(
                XYKeywordRule.owner_id == account.owner_id,
                XYKeywordRule.account_pk == account.id,
            )
            .order_by(XYKeywordRule.keyword, XYKeywordRule.item_id)
        )
        rows = await self.session.execute(stmt)
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
        return keywords

    async def replace_text_keywords(self, account: XYAccount, keywords: Sequence[dict]) -> None:
        normalized_entries: list[tuple[str, str, str | None]] = []
        seen: set[tuple[str, str]] = set()

        for entry in keywords:
            keyword = (entry.get("keyword") or "").strip()
            reply = (entry.get("reply") or "").strip()
            item_id = (entry.get("item_id") or "").strip() or None
            if not keyword:
                raise ValueError("关键词不能为空")

            key = (keyword.lower(), (item_id or "").lower())
            if key in seen:
                if item_id:
                    raise ValueError(f"关键词 '{keyword}'（商品ID: {item_id}） 在当前提交中重复")
                raise ValueError(f"关键词 '{keyword}'（通用关键词） 在当前提交中重复")
            seen.add(key)
            normalized_entries.append((keyword, reply, item_id))

        # Check for conflicts with image keywords
        image_rows = await self.session.execute(
            select(XYKeywordRule.keyword, XYKeywordRule.item_id).where(
                XYKeywordRule.owner_id == account.owner_id,
                XYKeywordRule.account_pk == account.id,
                func.lower(XYKeywordRule.reply_type) == "image",
            )
        )
        image_conflicts = {(row[0], (row[1] or "")) for row in image_rows.all()}
        for keyword, _, item_id in normalized_entries:
            comparison_key = (keyword, item_id or "")
            if comparison_key in image_conflicts:
                item_desc = f"商品ID: {item_id}" if item_id else "通用关键词"
                raise ValueError(f"关键词 '{keyword}'（{item_desc}） 已存在（图片关键词），无法保存为文本关键词")

        # Remove legacy text keywords and insert new ones
        await self.session.execute(
            delete(XYKeywordRule).where(
                XYKeywordRule.owner_id == account.owner_id,
                XYKeywordRule.account_pk == account.id,
                func.lower(func.coalesce(XYKeywordRule.reply_type, "text")) != "image",
            )
        )

        timestamp = datetime.now(timezone.utc)
        for keyword, reply, item_id in normalized_entries:
            self.session.add(
                XYKeywordRule(
                    owner_id=account.owner_id,
                    account_pk=account.id,
                    keyword=keyword,
                    reply_content=reply,
                    reply_type="TEXT",
                    item_id=item_id,
                    priority=100,
                    is_active=True,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )

        await self.session.commit()

    async def update_text_keyword(
        self,
        source_account: XYAccount,
        target_account: XYAccount,
        source_keyword: str,
        source_item_id: str | None,
        target_keyword: str,
        target_reply: str | None,
        target_item_id: str | None,
    ) -> None:
        normalized_source_keyword = (source_keyword or "").strip()
        normalized_source_item_id = (source_item_id or "").strip() or None
        normalized_target_keyword = (target_keyword or "").strip()
        normalized_target_reply = (target_reply or "").strip()
        normalized_target_item_id = (target_item_id or "").strip() or None

        if not normalized_target_keyword:
            raise ValueError("关键词不能为空")

        if source_account.owner_id != target_account.owner_id:
            raise ValueError("所属账号只能修改为同一用户下的账号")

        stmt = select(XYKeywordRule).where(
            XYKeywordRule.owner_id == source_account.owner_id,
            XYKeywordRule.account_pk == source_account.id,
            XYKeywordRule.keyword == normalized_source_keyword,
            XYKeywordRule.item_id == normalized_source_item_id,
            func.lower(func.coalesce(XYKeywordRule.reply_type, "text")) != "image",
        )
        result = await self.session.execute(stmt)
        existing_rule = result.scalars().first()

        if not existing_rule:
            raise ValueError("关键词不存在")

        conflict_stmt = select(XYKeywordRule).where(
            XYKeywordRule.owner_id == target_account.owner_id,
            XYKeywordRule.account_pk == target_account.id,
            XYKeywordRule.keyword == normalized_target_keyword,
            XYKeywordRule.item_id == normalized_target_item_id,
            XYKeywordRule.id != existing_rule.id,
        )
        conflict_result = await self.session.execute(conflict_stmt)
        conflict_rule = conflict_result.scalars().first()

        if conflict_rule:
            item_desc = f"商品ID: {normalized_target_item_id}" if normalized_target_item_id else "通用关键词"
            conflict_type = (conflict_rule.reply_type or "text").lower()
            if conflict_type == "image":
                raise ValueError(f"关键词 '{normalized_target_keyword}'（{item_desc}） 已存在（图片关键词），无法保存为文本关键词")
            raise ValueError(f"关键词 '{normalized_target_keyword}'（{item_desc}） 已存在")

        existing_rule.owner_id = target_account.owner_id
        existing_rule.account_pk = target_account.id
        existing_rule.keyword = normalized_target_keyword
        existing_rule.reply_content = normalized_target_reply
        existing_rule.reply_type = "TEXT"
        existing_rule.item_id = normalized_target_item_id
        existing_rule.updated_at = datetime.now(timezone.utc)

        await self.session.commit()

    async def delete_keyword(
        self,
        account: XYAccount,
        keyword: str,
        item_id: str | None = None,
    ) -> bool:
        """删除单个关键词（支持文本和图片类型）
        
        Args:
            account: 账号对象
            keyword: 关键词
            item_id: 商品ID（可选）
            
        Returns:
            是否删除成功
        """
        stmt = delete(XYKeywordRule).where(
            XYKeywordRule.owner_id == account.owner_id,
            XYKeywordRule.account_pk == account.id,
            XYKeywordRule.keyword == keyword,
            XYKeywordRule.item_id == (item_id if item_id else None),
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def list_keywords_by_account(self, account_id: str) -> list[XYKeywordRule]:
        """根据账号ID获取关键词规则列表
        
        Args:
            account_id: 账号标识（account_id字段）
            
        Returns:
            关键词规则列表
        """
        # 先获取账号
        account_stmt = select(XYAccount).where(XYAccount.account_id == account_id)
        account_result = await self.session.execute(account_stmt)
        account = account_result.scalars().first()
        
        if not account:
            return []
        
        # 获取关键词规则
        stmt = (
            select(XYKeywordRule)
            .where(
                XYKeywordRule.owner_id == account.owner_id,
                XYKeywordRule.account_pk == account.id,
                XYKeywordRule.is_active == True,
            )
            .order_by(XYKeywordRule.priority.desc(), XYKeywordRule.keyword)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_image_keyword(
        self,
        account: XYAccount,
        keyword: str,
        image_url: str,
        item_id: Optional[str] = None,
    ) -> None:
        """添加图片关键词"""
        # 统一处理 item_id，空字符串转为 None
        normalized_item_id = item_id if item_id and item_id.strip() else None
        
        # 检查是否已存在相同的关键词
        stmt = select(XYKeywordRule).where(
            XYKeywordRule.owner_id == account.owner_id,
            XYKeywordRule.account_pk == account.id,
            XYKeywordRule.keyword == keyword,
            XYKeywordRule.item_id == normalized_item_id,
        )
        result = await self.session.execute(stmt)
        existing = result.scalars().first()
        
        if existing:
            item_desc = f"商品ID: {normalized_item_id}" if normalized_item_id else "通用关键词"
            raise ValueError(f"关键词 '{keyword}'（{item_desc}） 已存在")
        
        timestamp = datetime.now(timezone.utc)
        self.session.add(
            XYKeywordRule(
                owner_id=account.owner_id,
                account_pk=account.id,
                keyword=keyword,
                reply_content="",
                reply_type="IMAGE",
                image_url=image_url,
                item_id=normalized_item_id,
                priority=100,
                is_active=True,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        await self.session.commit()
