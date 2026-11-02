"""
商品定时发布规则服务。

功能：
1. 校验账号、素材归属后新建或修改规则；
2. 按当前用户分页查询规则；
3. 提供新建弹窗所需的轻量账号和素材选项。
"""
from __future__ import annotations

from datetime import time
from typing import Any

from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.product_material import ProductMaterial
from common.models.scheduled_publish_rule import ScheduledPublishRule
from common.models.xy_account import XYAccount
from common.utils.time_utils import get_beijing_now_naive


IN_QUERY_CHUNK_SIZE = 1000


class ScheduledPublishRuleValidationError(ValueError):
    """定时发布规则业务校验错误。"""


class ScheduledPublishRuleService:
    """定时发布规则保存、查询及选项服务。"""

    def __init__(self, session: AsyncSession):
        """初始化服务。

        Args:
            session: 当前请求的数据库会话。
        """
        self.session = session

    async def list_options(self, owner_id: int) -> dict[str, list[dict[str, Any]]]:
        """查询当前用户可选择的账号和未删除素材。

        Args:
            owner_id: 当前用户ID。
        Returns:
            包含账号选项和素材选项的字典。
        """
        account_stmt = (
            select(
                XYAccount.account_id,
                XYAccount.display_name,
                XYAccount.remark,
                XYAccount.status,
            )
            .where(XYAccount.owner_id == owner_id)
            .order_by(XYAccount.account_id.asc())
        )
        material_stmt = (
            select(
                ProductMaterial.id,
                ProductMaterial.title,
                ProductMaterial.images,
            )
            .where(
                ProductMaterial.user_id == owner_id,
                ProductMaterial.is_deleted.is_(False),
            )
            .order_by(desc(ProductMaterial.created_at))
        )
        accounts = (await self.session.execute(account_stmt)).all()
        materials = (await self.session.execute(material_stmt)).all()
        logger.info(
            "定时发布规则选项查询完成: owner_id={}, account_count={}, material_count={}",
            owner_id,
            len(accounts),
            len(materials),
        )
        return {
            "accounts": [
                {
                    "account_id": row.account_id,
                    "display_name": row.display_name or row.remark or row.account_id,
                    "enabled": (row.status or "active").lower()
                    not in {"inactive", "disabled", "suspended", "deleted"},
                }
                for row in accounts
            ],
            "materials": [
                {
                    "id": row.id,
                    "title": row.title,
                    "image_url": self._first_material_image(row.images),
                }
                for row in materials
            ],
        }

    async def create(self, owner_id: int, data: dict[str, Any]) -> ScheduledPublishRule:
        """校验并创建定时发布规则。

        Args:
            owner_id: 当前用户ID。
            data: 已通过接口基础类型校验的规则数据。
        Returns:
            创建后的规则对象。
        Raises:
            ScheduledPublishRuleValidationError: 业务参数或资源归属不合法。
        """
        normalized = await self._validate_rule_payload(owner_id, data)

        now = get_beijing_now_naive()
        rule = ScheduledPublishRule(
            owner_id=owner_id,
            **normalized,
            is_enabled=True,
            is_deleted=False,
            created_at=now,
            updated_at=now,
        )
        self.session.add(rule)
        try:
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            logger.opt(exception=exc).error(
                "定时发布规则创建失败并已回滚: owner_id={}, rule_name={}",
                owner_id,
                normalized["rule_name"],
            )
            raise
        await self.session.refresh(rule)
        logger.info(
            "定时发布规则创建成功: owner_id={}, rule_id={}, account_count={}, material_count={}",
            owner_id,
            rule.id,
            len(normalized["account_ids"]),
            len(normalized["material_ids"]),
        )
        return rule

    async def update(
        self,
        owner_id: int,
        rule_id: int,
        data: dict[str, Any],
    ) -> ScheduledPublishRule:
        """修改当前用户的定时发布规则，不改变已生成的下次触发时间。

        Args:
            owner_id: 当前用户ID。
            rule_id: 规则ID。
            data: 修改后的完整规则配置。
        Returns:
            修改后的规则对象。
        Raises:
            ScheduledPublishRuleValidationError: 规则不存在或配置无效。
        """
        result = await self.session.execute(
            select(ScheduledPublishRule).where(
                ScheduledPublishRule.id == rule_id,
                ScheduledPublishRule.owner_id == owner_id,
                ScheduledPublishRule.is_deleted.is_(False),
            )
        )
        rule = result.scalar_one_or_none()
        if rule is None:
            raise ScheduledPublishRuleValidationError("定时发布规则不存在或无权修改")

        normalized = await self._validate_rule_payload(owner_id, data)
        for field, value in normalized.items():
            setattr(rule, field, value)
        rule.updated_at = get_beijing_now_naive()
        try:
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            logger.opt(exception=exc).error(
                "定时发布规则修改失败并已回滚: owner_id={}, rule_id={}",
                owner_id,
                rule_id,
            )
            raise
        await self.session.refresh(rule)
        logger.info("定时发布规则修改成功: owner_id={}, rule_id={}", owner_id, rule_id)
        return rule

    async def list_rules(
        self,
        owner_id: int,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """分页查询当前用户的定时发布规则。

        Args:
            owner_id: 当前用户ID。
            page: 页码。
            page_size: 每页条数。
            keyword: 规则名称关键词。
        Returns:
            统一分页数据。
        """
        page = max(page, 1)
        page_size = page_size if page_size in (10, 20, 50, 100) else 20
        conditions = [
            ScheduledPublishRule.owner_id == owner_id,
            ScheduledPublishRule.is_deleted.is_(False),
        ]
        normalized_keyword = (keyword or "").strip()
        if normalized_keyword:
            conditions.append(ScheduledPublishRule.rule_name.ilike(f"%{normalized_keyword}%"))

        total = (
            await self.session.execute(
                select(func.count()).select_from(ScheduledPublishRule).where(*conditions)
            )
        ).scalar() or 0
        stmt = (
            select(ScheduledPublishRule)
            .where(*conditions)
            .order_by(desc(ScheduledPublishRule.created_at), desc(ScheduledPublishRule.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        account_names, material_titles = await self._load_resource_labels(rows, owner_id)
        logger.info(
            "定时发布规则分页查询完成: owner_id={}, keyword={}, page={}, page_size={}, total={}",
            owner_id,
            normalized_keyword,
            page,
            page_size,
            int(total),
        )
        return {
            "list": [self._serialize(row, account_names, material_titles) for row in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "total_pages": (int(total) + page_size - 1) // page_size if total else 0,
        }

    async def _validate_resource_ownership(
        self,
        owner_id: int,
        account_ids: list[str],
        material_ids: list[int],
    ) -> None:
        """确认所选账号和素材全部属于当前用户。"""
        owned_accounts: set[str] = set()
        for id_chunk in self._chunked(account_ids):
            account_stmt = select(XYAccount.account_id).where(
                XYAccount.owner_id == owner_id,
                XYAccount.account_id.in_(id_chunk),
            )
            owned_accounts.update((await self.session.execute(account_stmt)).scalars().all())
        if owned_accounts != set(account_ids):
            raise ScheduledPublishRuleValidationError("部分账号不存在或不属于当前用户，请重新选择")

        owned_materials: set[int] = set()
        for id_chunk in self._chunked(material_ids):
            material_stmt = select(ProductMaterial.id).where(
                ProductMaterial.user_id == owner_id,
                ProductMaterial.id.in_(id_chunk),
                ProductMaterial.is_deleted.is_(False),
            )
            owned_materials.update((await self.session.execute(material_stmt)).scalars().all())
        if owned_materials != set(material_ids):
            raise ScheduledPublishRuleValidationError("部分素材不存在、已删除或不属于当前用户，请重新选择")

    async def _validate_rule_payload(
        self,
        owner_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """统一校验并规范化新建、修改规则的完整配置。"""
        rule_name = str(data.get("rule_name") or "").strip()
        account_ids = self._unique_strings(data.get("account_ids") or [])
        material_ids = self._unique_ints(data.get("material_ids") or [])
        if not rule_name:
            raise ScheduledPublishRuleValidationError("请输入规则名称")
        if not account_ids:
            raise ScheduledPublishRuleValidationError("请至少选择一个账号")
        if not material_ids:
            raise ScheduledPublishRuleValidationError("请至少选择一条素材")
        await self._validate_resource_ownership(owner_id, account_ids, material_ids)

        start_time = self._parse_time(str(data.get("trigger_start_time") or ""))
        end_time = self._parse_time(str(data.get("trigger_end_time") or ""))
        if self._time_minutes(start_time) >= self._time_minutes(end_time):
            raise ScheduledPublishRuleValidationError("触发开始时间必须早于结束时间")
        interval_min = int(data.get("interval_min_minutes") or 0)
        interval_max = int(data.get("interval_max_minutes") or 0)
        if interval_min <= 0 or interval_max <= 0:
            raise ScheduledPublishRuleValidationError("随机时间范围必须填写大于0的分钟数")
        if interval_min > interval_max:
            raise ScheduledPublishRuleValidationError("随机时间最小值不能大于最大值")
        return {
            "rule_name": rule_name,
            "account_ids": account_ids,
            "material_ids": material_ids,
            "trigger_start_time": start_time,
            "trigger_end_time": end_time,
            "interval_min_minutes": interval_min,
            "interval_max_minutes": interval_max,
        }

    async def _load_resource_labels(
        self,
        rules: list[ScheduledPublishRule],
        owner_id: int,
    ) -> tuple[dict[str, str], dict[int, str]]:
        """批量加载分页内规则使用的账号名称和素材标题。"""
        account_ids = {
            item
            for rule in rules
            for item in self._stored_account_ids(rule.account_ids)
        }
        material_ids = {
            item
            for rule in rules
            for item in self._stored_material_ids(rule.material_ids)
        }
        account_names: dict[str, str] = {}
        material_titles: dict[int, str] = {}
        for id_chunk in self._chunked(account_ids):
            stmt = select(
                XYAccount.account_id,
                XYAccount.display_name,
                XYAccount.remark,
            ).where(
                XYAccount.owner_id == owner_id,
                XYAccount.account_id.in_(id_chunk),
            )
            for row in (await self.session.execute(stmt)).all():
                account_names[row.account_id] = row.display_name or row.remark or row.account_id
        for id_chunk in self._chunked(material_ids):
            stmt = select(ProductMaterial.id, ProductMaterial.title).where(
                ProductMaterial.user_id == owner_id,
                ProductMaterial.id.in_(id_chunk),
            )
            material_titles.update(
                {int(row.id): row.title for row in (await self.session.execute(stmt)).all()}
            )
        return account_names, material_titles

    @staticmethod
    def _chunked(values: list[Any] | set[Any]) -> list[list[Any]]:
        """把大批量 ID 拆分，避免 MySQL 单条 IN 查询参数过多。"""
        items = list(values)
        return [
            items[offset:offset + IN_QUERY_CHUNK_SIZE]
            for offset in range(0, len(items), IN_QUERY_CHUNK_SIZE)
        ]

    @classmethod
    def _serialize(
        cls,
        rule: ScheduledPublishRule,
        account_names: dict[str, str],
        material_titles: dict[int, str],
    ) -> dict[str, Any]:
        """把规则对象转换为前端列表数据。"""
        account_ids = cls._stored_account_ids(rule.account_ids)
        material_ids = cls._stored_material_ids(rule.material_ids)
        return {
            "id": rule.id,
            "rule_name": rule.rule_name,
            "account_ids": account_ids,
            "account_names": [account_names.get(item, item) for item in account_ids],
            "material_ids": material_ids,
            "material_titles": [material_titles.get(item, f"素材#{item}") for item in material_ids],
            "trigger_start_time": rule.trigger_start_time.strftime("%H:%M") if rule.trigger_start_time else "",
            "trigger_end_time": rule.trigger_end_time.strftime("%H:%M") if rule.trigger_end_time else "",
            "interval_min_minutes": int(rule.interval_min_minutes or 0),
            "interval_max_minutes": int(rule.interval_max_minutes or 0),
            "is_enabled": bool(rule.is_enabled),
            "created_at": rule.created_at.isoformat(sep=" ", timespec="seconds") if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat(sep=" ", timespec="seconds") if rule.updated_at else None,
        }

    @staticmethod
    def _parse_time(value: str) -> time:
        """解析 HH:MM 时间字符串。"""
        try:
            return time.fromisoformat(value)
        except ValueError as exc:
            raise ScheduledPublishRuleValidationError("触发时间格式不正确") from exc

    @staticmethod
    def _time_minutes(value: time) -> int:
        """将时间转换为当天分钟数，便于比较先后。"""
        return value.hour * 60 + value.minute

    @staticmethod
    def _unique_strings(values: list[Any]) -> list[str]:
        """去除空值和重复字符串，并保留原选择顺序。"""
        normalized = (
            str(item).strip()
            for item in values
            if item is not None and str(item).strip()
        )
        return list(dict.fromkeys(normalized))

    @staticmethod
    def _unique_ints(values: list[Any]) -> list[int]:
        """去除重复整数，并保留原选择顺序。"""
        return list(dict.fromkeys(int(item) for item in values))

    @classmethod
    def _stored_account_ids(cls, value: Any) -> list[str]:
        """安全读取数据库中的账号ID数组，兼容字段补齐后的空值。"""
        if not isinstance(value, list):
            return []
        return cls._unique_strings(value)

    @staticmethod
    def _stored_material_ids(value: Any) -> list[int]:
        """安全读取数据库中的素材ID数组，忽略异常历史值。"""
        if not isinstance(value, list):
            return []
        normalized: list[int] = []
        seen: set[int] = set()
        for item in value:
            try:
                material_id = int(item)
            except (TypeError, ValueError):
                continue
            if material_id <= 0 or material_id in seen:
                continue
            seen.add(material_id)
            normalized.append(material_id)
        return normalized

    @staticmethod
    def _first_material_image(value: Any) -> str | None:
        """读取素材首图，兼容异常历史 JSON，避免选项接口整体失败。"""
        if not isinstance(value, list) or not value:
            return None
        first = value[0]
        if isinstance(first, str):
            return first.strip() or None
        if isinstance(first, dict):
            image_url = first.get("url") or first.get("image_url")
            return str(image_url).strip() if image_url else None
        return None
