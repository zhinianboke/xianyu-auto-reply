"""
定时发布记录查询服务。

功能：
1. 分页查询指定规则的发布记录；
2. 分页查询指定规则的触发记录；
3. 软删除指定规则的单条或多条触发记录；
4. 校验规则归属并补齐账号、素材和发布结果中文名称。
"""
from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scheduled_publish_rule_service import (
    ScheduledPublishRuleValidationError,
)
from common.models.data_dictionary import XYDataDictionary
from common.models.product_material import ProductMaterial
from common.models.scheduled_publish_record import ScheduledPublishRecord
from common.models.scheduled_publish_rule import ScheduledPublishRule
from common.models.scheduled_publish_trigger import ScheduledPublishTrigger
from common.models.xy_account import XYAccount
from common.utils.time_utils import get_beijing_now_naive, safe_isoformat


PUBLISH_RESULT_DICTIONARY = "scheduled_publish_result"


class ScheduledPublishRecordService:
    """定时发布规则关联记录分页查询服务。"""

    def __init__(self, session: AsyncSession):
        """初始化服务。

        Args:
            session: 当前请求的数据库会话。
        """
        self.session = session

    async def list_publish_records(
        self,
        owner_id: int,
        rule_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """分页查询规则的实际发布尝试记录。"""
        await self._ensure_owned_rule(owner_id, rule_id)
        page, page_size = self._normalize_page(page, page_size)
        conditions = [
            ScheduledPublishRecord.owner_id == owner_id,
            ScheduledPublishRecord.rule_id == rule_id,
        ]
        total = (
            await self.session.execute(
                select(func.count()).select_from(ScheduledPublishRecord).where(*conditions)
            )
        ).scalar() or 0
        rows = (
            await self.session.execute(
                select(ScheduledPublishRecord)
                .where(*conditions)
                .order_by(desc(ScheduledPublishRecord.created_at), desc(ScheduledPublishRecord.id))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        account_names = await self._load_account_names(
            owner_id, {row.account_id for row in rows}
        )
        material_titles = await self._load_material_titles(
            owner_id,
            {int(row.material_id) for row in rows if row.material_id is not None},
        )
        result_labels = await self._load_result_labels()
        logger.info(
            "定时发布记录分页查询完成: owner_id={}, rule_id={}, page={}, page_size={}, total={}",
            owner_id,
            rule_id,
            page,
            page_size,
            int(total),
        )
        return self._page_response(
            [
                {
                    "id": row.id,
                    "rule_id": row.rule_id,
                    "account_id": row.account_id,
                    "account_name": account_names.get(row.account_id, row.account_id),
                    "material_id": row.material_id,
                    "material_title": (
                        material_titles.get(int(row.material_id), f"素材#{row.material_id}")
                        if row.material_id is not None
                        else "无可用素材库"
                    ),
                    "publish_result": row.publish_result,
                    "publish_result_text": result_labels.get(
                        row.publish_result, row.publish_result
                    ),
                    "failure_reason": row.failure_reason,
                    "publish_date": row.publish_date.isoformat() if row.publish_date else None,
                    "created_at": safe_isoformat(row.created_at),
                    "updated_at": safe_isoformat(row.updated_at),
                }
                for row in rows
            ],
            int(total),
            page,
            page_size,
        )

    async def list_trigger_records(
        self,
        owner_id: int,
        rule_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """分页查询规则账号维度的下次触发记录。"""
        await self._ensure_owned_rule(owner_id, rule_id)
        page, page_size = self._normalize_page(page, page_size)
        conditions = [
            ScheduledPublishTrigger.owner_id == owner_id,
            ScheduledPublishTrigger.rule_id == rule_id,
            ScheduledPublishTrigger.is_deleted.is_(False),
        ]
        total = (
            await self.session.execute(
                select(func.count()).select_from(ScheduledPublishTrigger).where(*conditions)
            )
        ).scalar() or 0
        rows = (
            await self.session.execute(
                select(ScheduledPublishTrigger)
                .where(*conditions)
                .order_by(
                    ScheduledPublishTrigger.next_trigger_at.asc(),
                    ScheduledPublishTrigger.id.asc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        account_names = await self._load_account_names(
            owner_id, {row.account_id for row in rows}
        )
        logger.info(
            "定时发布触发记录分页查询完成: owner_id={}, rule_id={}, page={}, page_size={}, total={}",
            owner_id,
            rule_id,
            page,
            page_size,
            int(total),
        )
        return self._page_response(
            [
                {
                    "id": row.id,
                    "rule_id": row.rule_id,
                    "account_id": row.account_id,
                    "account_name": account_names.get(row.account_id, row.account_id),
                    "schedule_date": row.schedule_date.isoformat()
                    if row.schedule_date
                    else None,
                    "next_trigger_at": safe_isoformat(row.next_trigger_at),
                    "created_at": safe_isoformat(row.created_at),
                    "updated_at": safe_isoformat(row.updated_at),
                }
                for row in rows
            ],
            int(total),
            page,
            page_size,
        )

    async def delete_trigger_records(
        self,
        owner_id: int,
        rule_id: int,
        record_ids: list[int],
    ) -> dict[str, int]:
        """软删除当前用户指定规则下的触发记录。

        Args:
            owner_id: 当前用户ID。
            rule_id: 定时发布规则ID。
            record_ids: 待删除的触发记录ID列表。
        Returns:
            本次实际删除数量和请求记录数量。
        """
        await self._ensure_owned_rule(owner_id, rule_id)
        normalized_ids = list(dict.fromkeys(record_ids))
        rows = (
            await self.session.execute(
                select(ScheduledPublishTrigger)
                .where(
                    ScheduledPublishTrigger.owner_id == owner_id,
                    ScheduledPublishTrigger.rule_id == rule_id,
                    ScheduledPublishTrigger.id.in_(normalized_ids),
                    ScheduledPublishTrigger.is_deleted.is_(False),
                )
                .with_for_update()
            )
        ).scalars().all()
        updated_at = get_beijing_now_naive().replace(microsecond=0)
        for row in rows:
            row.is_deleted = True
            row.updated_at = updated_at
        await self.session.commit()
        logger.info(
            "定时发布触发记录软删除完成: owner_id={}, rule_id={}, requested={}, success_count={}",
            owner_id,
            rule_id,
            len(normalized_ids),
            len(rows),
        )
        return {
            "success_count": len(rows),
            "total_count": len(normalized_ids),
        }

    async def _ensure_owned_rule(self, owner_id: int, rule_id: int) -> None:
        """确认规则存在且属于当前用户。"""
        exists_result = await self.session.execute(
            select(ScheduledPublishRule.id).where(
                ScheduledPublishRule.id == rule_id,
                ScheduledPublishRule.owner_id == owner_id,
                ScheduledPublishRule.is_deleted.is_(False),
            )
        )
        if exists_result.scalar_one_or_none() is None:
            raise ScheduledPublishRuleValidationError("定时发布规则不存在或无权查看")

    async def _load_account_names(
        self, owner_id: int, account_ids: set[str]
    ) -> dict[str, str]:
        """批量加载账号显示名称。"""
        if not account_ids:
            return {}
        rows = (
            await self.session.execute(
                select(XYAccount.account_id, XYAccount.display_name, XYAccount.remark).where(
                    XYAccount.owner_id == owner_id,
                    XYAccount.account_id.in_(account_ids),
                )
            )
        ).all()
        return {
            row.account_id: row.display_name or row.remark or row.account_id
            for row in rows
        }

    async def _load_material_titles(
        self, owner_id: int, material_ids: set[int]
    ) -> dict[int, str]:
        """批量加载素材标题，包括已软删除的历史素材。"""
        if not material_ids:
            return {}
        rows = (
            await self.session.execute(
                select(ProductMaterial.id, ProductMaterial.title).where(
                    ProductMaterial.user_id == owner_id,
                    ProductMaterial.id.in_(material_ids),
                )
            )
        ).all()
        return {int(row.id): row.title for row in rows}

    async def _load_result_labels(self) -> dict[str, str]:
        """从数据字典加载发布结果中文名称。"""
        rows = (
            await self.session.execute(
                select(XYDataDictionary.dict_value, XYDataDictionary.dict_label).where(
                    XYDataDictionary.dict_type == PUBLISH_RESULT_DICTIONARY,
                    XYDataDictionary.enabled.is_(True),
                )
            )
        ).all()
        return {row.dict_value: row.dict_label for row in rows}

    @staticmethod
    def _normalize_page(page: int, page_size: int) -> tuple[int, int]:
        """规范分页参数。"""
        return max(page, 1), page_size if page_size in (10, 20, 50, 100) else 20

    @staticmethod
    def _page_response(
        rows: list[dict[str, Any]], total: int, page: int, page_size: int
    ) -> dict[str, Any]:
        """构造统一分页响应。"""
        return {
            "list": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }
