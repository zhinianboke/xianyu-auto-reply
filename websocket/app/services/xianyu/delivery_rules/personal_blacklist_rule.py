"""
个人黑名单规则

功能：
1. 查询个人黑名单表，检查买家是否在黑名单中
2. 支持三级匹配：商品级 > 账户级 > 用户级
3. 命中任一级别即拦截
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select, and_, or_

from common.db.session import async_session_maker
from common.models.xy_personal_blacklist import XYPersonalBlacklist
from common.models.xy_account import XYAccount
from app.services.xianyu.delivery_rules.base_rule import (
    BaseDeliveryRule,
    RuleCheckResult,
)
from app.services.xianyu.delivery_rules.context import DeliveryCheckContext


class PersonalBlacklistRule(BaseDeliveryRule):
    """个人黑名单规则：买家在个人黑名单中时拦截"""

    @property
    def rule_code(self) -> str:
        return "personal_blacklist"

    @property
    def rule_name(self) -> str:
        return "个人黑名单"

    @property
    def rule_description(self) -> str:
        return "检查买家是否在个人黑名单中（支持商品级、账户级、用户级匹配）"

    @property
    def default_config(self) -> dict:
        return {}

    async def check(self, context: DeliveryCheckContext) -> RuleCheckResult:
        """检查买家是否在个人黑名单中"""
        pf = context.log_prefix or f"【{context.cookie_id}】"

        try:
            hit_record = await self._find_blacklist_record(
                cookie_id=context.cookie_id,
                buyer_id=context.buyer_id,
                item_id=context.item_id,
                owner_id=context.owner_id,
            )
        except Exception as e:
            logger.error(f"{pf}[个人黑名单规则] 查询异常: {e}")
            # 查询异常不拦截，放行
            return RuleCheckResult(
                hit=False,
                rule_code=self.rule_code,
                rule_name=self.rule_name,
            )

        if hit_record:
            level = self._get_level_desc(hit_record)
            reason_text = hit_record.get("reason") or ""
            reason = f"买家在个人黑名单中（{level}）"
            if reason_text:
                reason += f"，原因：{reason_text}"
            logger.info(
                f"{pf}[个人黑名单规则] 命中：buyer_id={context.buyer_id}, "
                f"level={level}, blacklist_id={hit_record.get('id')}"
            )
            return RuleCheckResult(
                hit=True,
                rule_code=self.rule_code,
                rule_name=self.rule_name,
                reason=reason,
                extra_data={"blacklist_id": hit_record.get("id"), "level": level},
            )

        logger.info(
            f"{pf}[个人黑名单规则] 通过：buyer_id={context.buyer_id}, 不在黑名单中"
        )
        return RuleCheckResult(
            hit=False,
            rule_code=self.rule_code,
            rule_name=self.rule_name,
        )

    async def _find_blacklist_record(
        self,
        cookie_id: str,
        buyer_id: str,
        item_id: str | None,
        owner_id: int | None,
    ) -> dict | None:
        """查询买家是否在个人黑名单中

        匹配优先级：商品级 > 账户级 > 用户级
        只要命中任一已启用记录即返回

        Args:
            cookie_id: 卖家账号标识
            buyer_id: 买家ID
            item_id: 商品ID
            owner_id: 卖家所属用户ID

        Returns:
            命中的黑名单记录字典，未命中返回 None
        """
        async with async_session_maker() as session:
            # 先获取 owner_id（如果上下文中没有）
            if owner_id is None:
                stmt = select(XYAccount.owner_id).where(XYAccount.account_id == cookie_id).limit(1)
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                owner_id = row

            # 查询所有匹配的已启用黑名单记录
            # 匹配条件：owner_id + buyer_id + 已启用
            # 再按级别筛选：
            #   商品级：account_id = cookie_id AND item_id = item_id
            #   账户级：account_id = cookie_id AND item_id IS NULL
            #   用户级：account_id IS NULL AND item_id IS NULL
            conditions = [
                XYPersonalBlacklist.owner_id == owner_id,
                XYPersonalBlacklist.buyer_id == buyer_id,
                XYPersonalBlacklist.is_enabled == True,
            ]

            # 构建级别匹配条件
            level_conditions = []

            # 商品级
            if item_id:
                level_conditions.append(
                    and_(
                        XYPersonalBlacklist.account_id == cookie_id,
                        XYPersonalBlacklist.item_id == item_id,
                    )
                )

            # 账户级
            level_conditions.append(
                and_(
                    XYPersonalBlacklist.account_id == cookie_id,
                    XYPersonalBlacklist.item_id.is_(None),
                )
            )

            # 用户级
            level_conditions.append(
                and_(
                    XYPersonalBlacklist.account_id.is_(None),
                    XYPersonalBlacklist.item_id.is_(None),
                )
            )

            stmt = (
                select(XYPersonalBlacklist)
                .where(and_(*conditions), or_(*level_conditions))
                .limit(1)
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if record is None:
                return None

            return {
                "id": record.id,
                "account_id": record.account_id,
                "item_id": record.item_id,
                "reason": record.reason,
            }

    def _get_level_desc(self, record: dict) -> str:
        """获取命中级别描述"""
        if record.get("account_id") and record.get("item_id"):
            return "商品级"
        elif record.get("account_id"):
            return "账户级"
        else:
            return "用户级"
