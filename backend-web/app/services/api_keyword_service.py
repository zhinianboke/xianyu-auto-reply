"""API关键词配置服务：保存、软删除、账号权限校验及分页查询，不执行外部API。"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid5

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.services.account_service import AccountService
from common.db.retry import with_db_retry
from common.models.data_dictionary import XYDataDictionary
from common.models.xy_account import XYAccount
from common.models.xy_api_keyword_rule import (
    HTTP_METHOD_DICTIONARY,
    HTTP_METHODS,
    PARAMETER_DICTIONARY,
    PARAMETER_PLACEHOLDERS,
    XYApiKeywordRule,
)
from common.models.xy_catalog_item import XYCatalogItem
from common.schemas.api_keyword import (
    ApiKeywordBatchCreate,
    ApiKeywordConfig,
    ApiKeywordCreate,
    ApiKeywordUpdate,
)
from common.utils.time_utils import get_beijing_now_naive


class ApiKeywordService:
    """使用项目统一会话管理API关键词，所有配置按账号所属用户隔离。"""

    def __init__(self, session: AsyncSession) -> None:
        """接收依赖注入会话，不另建连接池。"""
        self.session = session

    @with_db_retry()
    async def get_options(self) -> dict[str, list[dict[str, str]]]:
        """返回方法和参数的中文字典及占位符，缺失时明确报错。"""
        try:
            rows = (await self.session.execute(select(XYDataDictionary).where(
                XYDataDictionary.dict_type.in_((HTTP_METHOD_DICTIONARY, PARAMETER_DICTIONARY)),
                XYDataDictionary.enabled.is_(True),
            ).order_by(XYDataDictionary.sort_order, XYDataDictionary.id))).scalars().all()
            methods = [
                {"value": row.dict_value, "label": row.dict_label}
                for row in rows if row.dict_type == HTTP_METHOD_DICTIONARY and row.dict_value in HTTP_METHODS
            ]
            parameters = [
                {"value": row.dict_value, "label": row.dict_label, "placeholder": PARAMETER_PLACEHOLDERS[row.dict_value]}
                for row in rows if row.dict_type == PARAMETER_DICTIONARY and row.dict_value in PARAMETER_PLACEHOLDERS
            ]
            if not methods or len(parameters) != len(PARAMETER_PLACEHOLDERS):
                raise ValueError("API关键词字典未初始化或已禁用，请检查数据库初始化结果")
            return {"methods": methods, "parameters": parameters}
        except Exception:
            await self.session.rollback()
            logger.exception("读取API关键词字典失败")
            raise

    async def _account_scope(self, owner_id: int | None, identifier: str) -> tuple[int, int]:
        """校验账号权限，返回主键和用户ID，避免回滚后复用失效ORM对象。"""
        try:
            account = await AccountService(self.session).get_account_for_user(owner_id, identifier)
            if not account:
                raise ValueError("账号不存在或无权操作，请选择自己的账号")
            return account.id, account.owner_id
        except Exception:
            await self.session.rollback()
            logger.exception("API关键词账号校验失败: owner_id={}, account={}", owner_id, identifier)
            raise

    async def _validate_items(self, owner_id: int, account_pk: int, item_ids: list[str]) -> None:
        """校验新绑定商品均属于当前账号和用户；参数为商品列表，失败抛出中文错误。"""
        if not item_ids:
            return
        existing = set((await self.session.scalars(select(XYCatalogItem.item_id).where(
            XYCatalogItem.owner_id == owner_id,
            XYCatalogItem.account_pk == account_pk,
            XYCatalogItem.item_id.in_(item_ids),
        ))).all())
        if set(item_ids) - existing:
            raise ValueError("选择的商品不存在或不属于当前账号，请重新选择")

    @staticmethod
    def _editable_values(rule: XYApiKeywordRule) -> dict[str, Any]:
        """统一提取表单字段，JSON空值与前端回显一致，不包含账号、幂等标识及时间。"""
        values = {name: getattr(rule, name) for name in ApiKeywordConfig.model_fields}
        values.update(headers=rule.headers or {}, params=rule.params or {})
        return values

    @staticmethod
    def _values_revision(values: dict[str, Any]) -> str:
        """生成配置内容版本，JSON的数字、布尔等类型参与比较，字段顺序不影响版本。"""
        serialized = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _revision(cls, rule: XYApiKeywordRule) -> str:
        """使用配置内容生成并发校验版本，避免MySQL秒级时间戳无法区分连续修改。"""
        return cls._values_revision(cls._editable_values(rule))

    @staticmethod
    def _detail(rule: XYApiKeywordRule, identifier: str) -> dict[str, Any]:
        """序列化配置，隐藏内部幂等标识，ID使用字符串避免前端精度丢失。"""
        return {
            "id": str(rule.id), "account_id": identifier, "keyword": rule.keyword,
            "item_id": rule.item_id or "",
            "url": rule.url, "method": rule.method, "timeout": rule.timeout,
            "headers": rule.headers or {}, "params": rule.params or {},
            "response_field": rule.response_field,
            "sync_confirm_delivery": rule.sync_confirm_delivery,
            "trigger_after_order": rule.trigger_after_order,
            "follow_order_quantity": rule.follow_order_quantity,
            "skip_same_message": rule.skip_same_message,
            "created_at": rule.created_at.isoformat(), "updated_at": rule.updated_at.isoformat(),
            "revision": ApiKeywordService._revision(rule),
        }

    async def _get_rule(
        self, owner_id: int | None, identifier: str, rule_id: int, *,
        for_update: bool = False, include_deleted: bool = False,
    ) -> XYApiKeywordRule:
        """按账号权限及用户隔离读取配置；修改时锁行，删除重试可读取已删除记录。"""
        account_pk, account_owner = await self._account_scope(owner_id, identifier)
        stmt = select(XYApiKeywordRule).where(
            XYApiKeywordRule.id == rule_id,
            XYApiKeywordRule.account_id == account_pk,
            XYApiKeywordRule.owner_id == account_owner,
        ).execution_options(populate_existing=True)
        if not include_deleted:
            stmt = stmt.where(XYApiKeywordRule.is_deleted.is_(False))
        if for_update:
            stmt = stmt.with_for_update()
        rule = (await self.session.execute(stmt)).scalar_one_or_none()
        if rule is None:
            raise ValueError("API关键词不存在或无权操作，请刷新列表后重试")
        return rule

    @with_db_retry()
    async def get_detail(self, owner_id: int | None, identifier: str, rule_id: int) -> dict[str, Any]:
        """读取最新配置及版本供编辑回显，不触发外部请求。"""
        try:
            return self._detail(await self._get_rule(owner_id, identifier, rule_id), identifier)
        except Exception:
            await self.session.rollback()
            logger.exception("API关键词详情查询失败: owner_id={}, account={}, id={}", owner_id, identifier, rule_id)
            raise

    @with_db_retry(retry_on_lock_contention=True)
    async def update(self, owner_id: int | None, identifier: str, rule_id: int, payload: ApiKeywordUpdate) -> dict[str, Any]:
        """校验并保存原配置；保持主键和账号，防并发覆盖及网络重试重复写入。

        Args:
            owner_id: 用户权限范围，管理员为None。
            identifier: 原配置所属账号。
            rule_id: 原配置主键。
            payload: 完整可编辑字段和读取时的版本。
        Returns:
            保存后的配置详情及版本；失败回滚并抛出中文错误。
        """
        values = payload.model_dump(mode="json", exclude={"expected_revision"})
        try:
            options = await self.get_options()
            if payload.method not in {item["value"] for item in options["methods"]}:
                raise ValueError("该请求方法已禁用，请重新选择")
            rule = await self._get_rule(owner_id, identifier, rule_id, for_update=True)
            revision = self._revision(rule)
            if revision == self._values_revision(values):
                # 上次保存响应丢失后重试相同内容，返回成功并释放行锁。
                detail = self._detail(rule, identifier)
                await self.session.commit()
                return detail
            if revision != payload.expected_revision:
                raise ValueError("该API配置已被修改，请关闭编辑窗口后重新打开再保存")
            if payload.item_id and payload.item_id != rule.item_id:
                await self._validate_items(rule.owner_id, rule.account_id, [payload.item_id])
            for name, value in values.items():
                setattr(rule, name, value)
                if name in {"headers", "params"}:
                    # ORM默认把JSON中的false与0视为相等，显式标记防止类型修改漏写入。
                    flag_modified(rule, name)
            rule.updated_at = get_beijing_now_naive().replace(microsecond=0)
            await self.session.flush()
            detail = self._detail(rule, identifier)
            await self.session.commit()
            logger.info("API关键词修改成功: owner_id={}, account={}, id={}, config={}", owner_id, identifier, rule_id, values)
            return detail
        except Exception:
            await self.session.rollback()
            logger.exception("API关键词修改失败: owner_id={}, account={}, id={}, config={}", owner_id, identifier, rule_id, values)
            raise

    @with_db_retry(retry_on_lock_contention=True)
    async def delete(self, owner_id: int | None, identifier: str, rule_id: int) -> dict[str, str]:
        """按原账号和用户权限软删除配置，保留原数据，重复请求返回成功。

        Args:
            owner_id: 用户权限范围，管理员为None。
            identifier: 配置所属账号标识。
            rule_id: 待删除配置主键。
        Returns:
            已删除配置的主键及账号；失败回滚并抛出中文错误。
        """
        try:
            rule = await self._get_rule(
                owner_id, identifier, rule_id, for_update=True, include_deleted=True,
            )
            already_deleted = rule.is_deleted
            if not already_deleted:
                rule.is_deleted = True
                rule.updated_at = get_beijing_now_naive().replace(microsecond=0)
            data = {"id": str(rule.id), "account_id": identifier}
            await self.session.commit()
            logger.info("API关键词软删除成功: owner_id={}, account={}, id={}, already_deleted={}",
                        owner_id, identifier, rule_id, already_deleted)
            return data
        except Exception:
            await self.session.rollback()
            logger.exception("API关键词软删除失败: owner_id={}, account={}, id={}", owner_id, identifier, rule_id)
            raise

    @classmethod
    def _check_same_request(cls, rule: XYApiKeywordRule, values: dict[str, Any]) -> None:
        """复用配置内容版本校验重试，拒绝将JSON数字和布尔值视为相同内容。"""
        current = {**cls._editable_values(rule), "request_id": rule.request_id}
        if cls._values_revision(current) != cls._values_revision(values):
            raise ValueError("该请求已保存过其他内容，请关闭窗口后重新新建")

    @with_db_retry()
    async def create(self, owner_id: int | None, identifier: str, payload: ApiKeywordCreate) -> dict[str, Any]:
        """保存配置，相同请求标识可安全重试，不会重复插入。

        Args:
            owner_id: 权限范围，管理员为None。
            identifier: 页面选中的账号标识。
            payload: 已校验配置及内部请求标识。
        Returns:
            已提交的配置详情；失败回滚并抛出错误。
        """
        return (await self._create_configs(owner_id, identifier, [payload.model_dump(mode="json")]))[0]

    @with_db_retry()
    async def create_batch(
        self, owner_id: int | None, identifier: str, payload: ApiKeywordBatchCreate,
    ) -> dict[str, Any]:
        """多选商品原子保存；参数为账号和批量表单，返回各商品配置及保存条数。"""
        item_ids = sorted(payload.item_ids)
        config = payload.config.model_dump(mode="json")
        values = [{
            **config, "item_id": item_id,
            "request_id": str(payload.config.request_id if index == 0 else uuid5(payload.config.request_id, item_id)),
        } for index, item_id in enumerate(item_ids)]
        items = await self._create_configs(owner_id, identifier, values)
        return {"list": items, "total": len(items)}

    @classmethod
    def _saved_configs(cls, rules: list[XYApiKeywordRule], values: list[dict], identifier: str, item_scope: str) -> list[dict]:
        """检查单条或批量重试内容；参数为已存配置和请求，返回按请求排序的详情。"""
        by_request = {rule.request_id: rule for rule in rules}
        if len(by_request) != len(values):
            raise ValueError("该请求已保存过其他商品配置，请关闭窗口后重新新建")
        details = []
        for value in values:
            rule = by_request[value["request_id"]]
            if rule.request_item_scope and rule.request_item_scope != item_scope:
                raise ValueError("该请求已保存过其他商品配置，请关闭窗口后重新新建")
            cls._check_same_request(rule, value)
            details.append(cls._detail(rule, identifier))
        return details

    async def _create_configs(self, owner_id: int | None, identifier: str, values: list[dict]) -> list[dict]:
        """单条与多商品保存共用事务、权限及幂等检查；参数为配置列表，返回已提交详情。"""
        account_pk, account_owner = await self._account_scope(owner_id, identifier)
        item_scope = self._values_revision({"item_ids": sorted(value["item_id"] or "" for value in values)})
        existing_stmt = select(XYApiKeywordRule).where(
            XYApiKeywordRule.request_id.in_([value["request_id"] for value in values]),
            XYApiKeywordRule.owner_id == account_owner,
            XYApiKeywordRule.account_id == account_pk,
            XYApiKeywordRule.is_deleted.is_(False),
        )
        try:
            existing = list((await self.session.scalars(existing_stmt)).all())
            if existing:
                details = self._saved_configs(existing, values, identifier, item_scope)
                await self.session.commit()
                return details
            options = await self.get_options()
            if values[0]["method"] not in {item["value"] for item in options["methods"]}:
                raise ValueError("该请求方法已禁用，请重新选择")
            await self._validate_items(account_owner, account_pk, [value["item_id"] for value in values if value["item_id"]])
            rules = [XYApiKeywordRule(owner_id=account_owner, account_id=account_pk, request_item_scope=item_scope, **value) for value in values]
            self.session.add_all(rules)
            await self.session.flush()
            details = [self._detail(rule, identifier) for rule in rules]
            await self.session.commit()
            logger.info("API关键词保存成功: owner_id={}, account={}, ids={}, config={}",
                        account_owner, identifier, [item["id"] for item in details], values)
            return details
        except IntegrityError:
            await self.session.rollback()
            try:
                existing = list((await self.session.scalars(existing_stmt)).all())
                if existing:
                    details = self._saved_configs(existing, values, identifier, item_scope)
                    await self.session.commit()
                    return details
                logger.exception("API关键词标识冲突: account={}, config={}", identifier, values)
                raise ValueError("保存请求标识冲突，请关闭窗口后重新新建") from None
            except Exception:
                await self.session.rollback()
                raise
        except Exception:
            await self.session.rollback()
            logger.exception("API关键词保存失败: owner_id={}, account={}, config={}", account_owner, identifier, values)
            raise

    @with_db_retry()
    async def list_paginated(self, owner_id: int | None, identifier: str, page: int, page_size: int) -> dict[str, Any]:
        """分页读取未删除配置，普通用户只能读取本人账号的记录。"""
        try:
            conditions = [XYApiKeywordRule.is_deleted.is_(False), XYApiKeywordRule.owner_id == XYAccount.owner_id]
            if owner_id is not None:
                conditions.append(XYApiKeywordRule.owner_id == owner_id)
            if identifier:
                account_pk, _ = await self._account_scope(owner_id, identifier)
                conditions.append(XYApiKeywordRule.account_id == account_pk)
            base = select(XYApiKeywordRule, XYAccount.account_id).join(
                XYAccount, XYAccount.id == XYApiKeywordRule.account_id,
            ).where(*conditions)
            total = (await self.session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
            rows = (await self.session.execute(base.order_by(XYApiKeywordRule.id.desc())
                    .offset((page - 1) * page_size).limit(page_size))).all()
            return {"list": [self._detail(rule, account_id) for rule, account_id in rows],
                    "total": total, "page": page, "page_size": page_size}
        except Exception:
            await self.session.rollback()
            logger.exception("API关键词查询失败: owner_id={}, account={}, page={}", owner_id, identifier, page)
            raise
