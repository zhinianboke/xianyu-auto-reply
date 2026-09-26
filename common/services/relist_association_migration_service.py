"""自动续售成功后的商品关联迁移服务。"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.card_item_relation import CardItemRelation
from common.models.default_reply import DefaultReply
from common.models.relist_association_migration import RelistAssociationMigration
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.models.xy_delivery_block_rule import XYDeliveryBlockRule
from common.models.xy_keyword_rule import XYKeywordRule
from common.models.xy_personal_blacklist import XYPersonalBlacklist


class RelistAssociationMigrationService:
    """将持续配置幂等追加到新商品，支持失败后只补偿未完成步骤。"""

    STEPS = (
        "catalog_item",
        "card_relations",
        "keyword_rules",
        "default_replies",
        "ai_prompt",
        "delivery_exclusions",
        "personal_blacklist",
    )

    # 站外联系方式定位字段必须随回复内容一起复制：缺失时回复链路校验失败，
    # 规则匹配成功却静默零回复。
    LOCATION_FIELDS = (
        "location_name",
        "location_longitude",
        "location_latitude",
        "location_title",
        "location_subtitle",
    )
    KEYWORD_REPLY_FIELDS = ("reply_type", "reply_content", "image_url", *LOCATION_FIELDS)
    DEFAULT_REPLY_FIELDS = (
        "reply_type",
        "reply_content",
        "reply_image",
        "api_url",
        "api_timeout",
        "reply_once",
        "enabled",
        *LOCATION_FIELDS,
    )

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _copy_reply_fields(src: Any, dst: Any, fields: tuple[str, ...]) -> None:
        """按字段名整体复制回复配置，避免两处复制逻辑各自维护时漏掉新增字段。"""
        for name in fields:
            setattr(dst, name, getattr(src, name, None))

    @staticmethod
    def _missing_location_fields(reply: Any) -> list[str]:
        """返回缺失的定位字段名（副标题可选，与回复链路校验一致）。"""
        return [
            name
            for name in ("location_name", "location_longitude", "location_latitude", "location_title")
            if not str(getattr(reply, name, None) or "").strip()
        ]

    @classmethod
    def _ensure_keyword_reply_usable(cls, rule: Any) -> None:
        """复制后的启用规则必须仍能产生回复，否则显式失败而非留下零回复规则。"""
        if not rule.is_active:
            return
        reply_type = str(rule.reply_type or "text").strip().lower()
        if reply_type == "external_contact":
            missing = cls._missing_location_fields(rule)
            if missing:
                raise ValueError(
                    f"关键词规则「{rule.keyword}」为站外联系方式但缺少定位字段"
                    f"（{'、'.join(missing)}），迁移后会静默零回复"
                )
        elif reply_type == "image":
            # 回复链路在图片地址为空时会退化为文本回复，故仅两者皆空才算无效。
            if not str(rule.image_url or "").strip() and not str(rule.reply_content or "").strip():
                raise ValueError(f"关键词规则「{rule.keyword}」的图片地址与回复内容均为空，迁移后会静默零回复")
        elif not str(rule.reply_content or "").strip():
            raise ValueError(f"关键词规则「{rule.keyword}」的回复内容为空，迁移后会静默零回复")

    @classmethod
    def _ensure_default_reply_usable(cls, reply: Any) -> None:
        """复制后的启用默认回复必须仍能产生回复，否则显式失败而非留下零回复配置。"""
        if not reply.enabled:
            return
        reply_type = str(reply.reply_type or "text").strip().lower()
        if reply_type == "external_contact":
            missing = cls._missing_location_fields(reply)
            if missing:
                raise ValueError(f"商品默认回复为站外联系方式但缺少定位字段（{'、'.join(missing)}），迁移后会静默零回复")
        elif reply_type == "api":
            if not str(reply.api_url or "").strip():
                raise ValueError("商品默认回复为接口类型但缺少 API 地址，迁移后会静默零回复")
        elif not str(reply.reply_content or "").strip() and not str(reply.reply_image or "").strip():
            raise ValueError("商品默认回复的内容与图片均为空，迁移后会静默零回复")

    async def migrate_after_relist(
        self,
        *,
        owner_id: int,
        account_id: str,
        material_id: int,
        old_item_id: str,
        new_item_id: str,
        event_id: int,
        source_type: str | None = None,
    ) -> dict[str, Any]:
        """执行续售后关联迁移并返回每一步状态。"""
        # 当前自动续售入口只处理商品素材；保留 source_type 参数以兼容返佣素材
        # 后置扩展，但没有明确来源映射时不改写 FYMaterial，避免误关联返佣数据。
        del material_id, source_type
        account = (
            await self.session.execute(
                select(XYAccount).where(XYAccount.owner_id == owner_id, XYAccount.account_id == account_id)
            )
        ).scalars().first()
        if not account:
            return {"success": False, "message": "续售关联迁移失败：闲鱼账号不存在", "steps": {}}

        handlers: dict[str, Callable[[], Awaitable[None]]] = {
            "catalog_item": lambda: self._ensure_catalog_item(owner_id, account.id, new_item_id),
            "card_relations": lambda: self._migrate_card_relations(owner_id, old_item_id, new_item_id),
            "keyword_rules": lambda: self._migrate_keyword_rules(owner_id, account.id, old_item_id, new_item_id),
            "default_replies": lambda: self._migrate_default_replies(account_id, old_item_id, new_item_id),
            "ai_prompt": lambda: self._migrate_ai_prompt(owner_id, account.id, old_item_id, new_item_id),
            "delivery_exclusions": lambda: self._migrate_delivery_exclusions(owner_id, account_id, old_item_id, new_item_id),
            "personal_blacklist": lambda: self._migrate_personal_blacklist(owner_id, account_id, old_item_id, new_item_id),
        }
        statuses: dict[str, str] = {}
        for step in self.STEPS:
            record = await self._get_step(event_id, owner_id, step)
            if record.status == "success":
                statuses[step] = "success"
                continue
            record.status = "running"
            record.attempt_count = int(record.attempt_count or 0) + 1
            try:
                await handlers[step]()
                record.status = "success"
                record.error_message = None
                statuses[step] = "success"
                await self.session.commit()
            except Exception as exc:
                await self.session.rollback()
                record = await self._get_step(event_id, owner_id, step)
                record.status = "failed"
                record.error_message = str(exc)[:1000]
                await self.session.commit()
                statuses[step] = "failed"
                logger.error("[自动续售] 关联迁移失败 event_id={} step={} error={}", event_id, step, exc)
                return {"success": False, "message": f"关联迁移失败（{step}）：{exc}", "steps": statuses}
        return {"success": True, "message": "关联迁移完成", "steps": statuses}

    async def _ensure_catalog_item(self, owner_id: int, account_pk: int, new_item_id: str) -> None:
        """确认发布后的新商品已同步到本地目录，避免关联迁移早于商品同步。"""
        exists = (
            await self.session.execute(
                select(XYCatalogItem.id).where(
                    XYCatalogItem.owner_id == owner_id,
                    XYCatalogItem.account_pk == account_pk,
                    XYCatalogItem.item_id == new_item_id,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            raise ValueError("新商品目录尚未同步，稍后重试关联迁移")

    async def _get_step(self, event_id: int, owner_id: int, step: str) -> RelistAssociationMigration:
        record = (
            await self.session.execute(
                select(RelistAssociationMigration)
                .where(
                    RelistAssociationMigration.event_id == event_id,
                    RelistAssociationMigration.user_id == owner_id,
                    RelistAssociationMigration.step == step,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if record:
            return record
        record = RelistAssociationMigration(event_id=event_id, user_id=owner_id, step=step, status="pending")
        self.session.add(record)
        try:
            await self.session.flush()
            return record
        except IntegrityError:
            # 同一事件的补偿任务可能在极端并发下同时初始化步骤；唯一键竞争时
            # 回滚临时插入并读取已提交记录，避免把可恢复竞争误报为迁移失败。
            await self.session.rollback()
            existing = (
                await self.session.execute(
                    select(RelistAssociationMigration)
                    .where(
                        RelistAssociationMigration.event_id == event_id,
                        RelistAssociationMigration.user_id == owner_id,
                        RelistAssociationMigration.step == step,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if existing:
                return existing
            raise

    async def _migrate_card_relations(self, owner_id: int, old_item_id: str, new_item_id: str) -> None:
        rows = (
            await self.session.execute(
                select(CardItemRelation).where(
                    CardItemRelation.user_id == owner_id,
                    CardItemRelation.item_id == old_item_id,
                )
            )
        ).scalars().all()
        for row in rows:
            # 历史表允许 NULL，而当前表默认使用 0 表示自有卡券。两者视为同一
            # 个来源进行去重，并将新关系规范化为当前表可接受的 0。
            source_dock_record_id = row.dock_record_id if row.dock_record_id is not None else 0
            source_condition = (
                CardItemRelation.source.is_(None)
                if row.source is None
                else CardItemRelation.source == row.source
            )
            dock_record_condition = (
                or_(
                    CardItemRelation.dock_record_id.is_(None),
                    CardItemRelation.dock_record_id == 0,
                )
                if row.dock_record_id is None
                else CardItemRelation.dock_record_id == row.dock_record_id
            )
            exists = (
                await self.session.execute(
                    select(CardItemRelation.id).where(
                        CardItemRelation.user_id == owner_id,
                        CardItemRelation.card_id == row.card_id,
                        CardItemRelation.item_id == new_item_id,
                        source_condition,
                        dock_record_condition,
                    )
                )
            ).scalar_one_or_none()
            if not exists:
                self.session.add(
                    CardItemRelation(
                        user_id=row.user_id,
                        card_id=row.card_id,
                        item_id=new_item_id,
                        source=row.source,
                        dock_record_id=source_dock_record_id,
                    )
                )
        await self.session.flush()

    async def _migrate_keyword_rules(self, owner_id: int, account_pk: int, old_item_id: str, new_item_id: str) -> None:
        rows = (
            await self.session.execute(
                select(XYKeywordRule).where(
                    XYKeywordRule.owner_id == owner_id,
                    XYKeywordRule.account_pk == account_pk,
                    XYKeywordRule.item_id == old_item_id,
                )
            )
        ).scalars().all()
        for row in rows:
            exists = (
                await self.session.execute(
                    select(XYKeywordRule.id).where(
                        XYKeywordRule.owner_id == owner_id,
                        XYKeywordRule.account_pk == account_pk,
                        XYKeywordRule.item_id == new_item_id,
                        XYKeywordRule.keyword == row.keyword,
                    )
                )
            ).scalar_one_or_none()
            if not exists:
                new_rule = XYKeywordRule(
                    owner_id=owner_id,
                    account_pk=account_pk,
                    keyword=row.keyword,
                    item_id=new_item_id,
                    priority=row.priority,
                    is_active=row.is_active,
                )
                self._copy_reply_fields(row, new_rule, self.KEYWORD_REPLY_FIELDS)
                self._ensure_keyword_reply_usable(new_rule)
                self.session.add(new_rule)
        await self.session.flush()

    async def _migrate_default_replies(self, account_id: str, old_item_id: str, new_item_id: str) -> None:
        rows = (
            await self.session.execute(
                select(DefaultReply).where(DefaultReply.account_id == account_id, DefaultReply.item_id == old_item_id)
            )
        ).scalars().all()
        for row in rows:
            exists = (
                await self.session.execute(
                    select(DefaultReply.id).where(DefaultReply.account_id == account_id, DefaultReply.item_id == new_item_id)
                )
            ).scalar_one_or_none()
            if not exists:
                new_reply = DefaultReply(account_id=account_id, item_id=new_item_id)
                self._copy_reply_fields(row, new_reply, self.DEFAULT_REPLY_FIELDS)
                self._ensure_default_reply_usable(new_reply)
                self.session.add(new_reply)
        await self.session.flush()

    async def _migrate_ai_prompt(self, owner_id: int, account_pk: int, old_item_id: str, new_item_id: str) -> None:
        old_item = (
            await self.session.execute(
                select(XYCatalogItem).where(
                    XYCatalogItem.owner_id == owner_id,
                    XYCatalogItem.account_pk == account_pk,
                    XYCatalogItem.item_id == old_item_id,
                )
            )
        ).scalar_one_or_none()
        new_item = (
            await self.session.execute(
                select(XYCatalogItem).where(
                    XYCatalogItem.owner_id == owner_id,
                    XYCatalogItem.account_pk == account_pk,
                    XYCatalogItem.item_id == new_item_id,
                )
            )
        ).scalar_one_or_none()
        if old_item and old_item.ai_prompt:
            if not new_item:
                raise ValueError("新商品目录尚未同步，稍后重试关联迁移")
            new_item.ai_prompt = old_item.ai_prompt
            await self.session.flush()

    async def _migrate_delivery_exclusions(self, owner_id: int, account_id: str, old_item_id: str, new_item_id: str) -> None:
        account = (
            await self.session.execute(select(XYAccount).where(XYAccount.owner_id == owner_id, XYAccount.account_id == account_id))
        ).scalars().first()
        if account:
            values = list(account.delivery_disabled_excluded_items or [])
            if old_item_id in values and new_item_id not in values:
                account.delivery_disabled_excluded_items = values + [new_item_id]
        rules = (
            await self.session.execute(select(XYDeliveryBlockRule).where(XYDeliveryBlockRule.account_id == account_id))
        ).scalars().all()
        for rule in rules:
            values = list(rule.excluded_item_ids or [])
            if old_item_id in values and new_item_id not in values:
                rule.excluded_item_ids = values + [new_item_id]
        await self.session.flush()

    async def _migrate_personal_blacklist(self, owner_id: int, account_id: str, old_item_id: str, new_item_id: str) -> None:
        rows = (
            await self.session.execute(
                select(XYPersonalBlacklist).where(
                    XYPersonalBlacklist.owner_id == owner_id,
                    XYPersonalBlacklist.account_id == account_id,
                    XYPersonalBlacklist.item_id == old_item_id,
                )
            )
        ).scalars().all()
        for row in rows:
            exists = (
                await self.session.execute(
                    select(XYPersonalBlacklist.id).where(
                        XYPersonalBlacklist.owner_id == owner_id,
                        XYPersonalBlacklist.account_id == account_id,
                        XYPersonalBlacklist.buyer_id == row.buyer_id,
                        XYPersonalBlacklist.item_id == new_item_id,
                    )
                )
            ).scalar_one_or_none()
            if not exists:
                self.session.add(
                    XYPersonalBlacklist(
                        owner_id=owner_id,
                        account_id=account_id,
                        buyer_id=row.buyer_id,
                        buyer_nick=row.buyer_nick,
                        item_id=new_item_id,
                        reason=row.reason,
                        is_enabled=row.is_enabled,
                    )
                )
        await self.session.flush()
