"""
买家在同用户其他账号已有订单规则

功能：
1. 查询本地订单表，检查同一买家在当前用户名下所有账号中是否已有其他订单
2. 存在其他订单时命中拦截（用于防止同一买家在不同店铺重复下单/薅羊毛）
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select, func, and_

from common.db.session import async_session_maker
from common.models.xy_order import XYOrder
from app.services.xianyu.delivery_rules.base_rule import (
    BaseDeliveryRule,
    RuleCheckResult,
)
from app.services.xianyu.delivery_rules.context import DeliveryCheckContext


class BuyerHasOrderGlobalRule(BaseDeliveryRule):
    """买家在同用户其他账号已有订单规则：同一买家在同一用户名下所有账号中已有其他订单时拦截"""

    @property
    def rule_code(self) -> str:
        return "buyer_has_order_global"

    @property
    def rule_name(self) -> str:
        return "买家在同用户其他账号已有订单"

    @property
    def rule_description(self) -> str:
        return "检查买家在当前用户名下所有账号中是否已有其他订单，有则禁止发货"

    @property
    def default_config(self) -> dict:
        # same_item_only: 是否仅限同商品订单才算命中
        return {"same_item_only": False}

    async def check(self, context: DeliveryCheckContext) -> RuleCheckResult:
        """检查买家在同用户其他账号下是否已有其他订单"""
        pf = context.log_prefix or f"【{context.cookie_id}】"
        same_item_only = context.rule_config.get("same_item_only", False)

        # owner_id / buyer_id 缺失保护：无所属用户或买家ID时直接放行
        # （owner 维度跨账号查询，空值会误拦该用户名下大量订单，必须防护）
        if context.owner_id is None or not context.buyer_id:
            logger.warning(
                f"{pf}[同用户已有订单规则] owner_id 或 buyer_id 缺失，放行不拦截"
            )
            return RuleCheckResult(
                hit=False,
                rule_code=self.rule_code,
                rule_name=self.rule_name,
            )

        try:
            order_count = await self._count_owner_orders(
                owner_id=context.owner_id,
                buyer_id=context.buyer_id,
                exclude_order_no=context.order_no,
                item_id=context.item_id if same_item_only else None,
            )
        except Exception as e:
            logger.error(f"{pf}[同用户已有订单规则] 查询异常: {e}")
            # 查询异常不拦截，放行
            return RuleCheckResult(
                hit=False,
                rule_code=self.rule_code,
                rule_name=self.rule_name,
            )

        if order_count > 0:
            reason = f"买家在您名下其他账号已有{order_count}笔订单，禁止发货"
            logger.info(
                f"{pf}[同用户已有订单规则] 命中：buyer_id={context.buyer_id}, "
                f"owner_id={context.owner_id}, order_count={order_count}, "
                f"same_item_only={same_item_only}"
            )
            return RuleCheckResult(
                hit=True,
                rule_code=self.rule_code,
                rule_name=self.rule_name,
                reason=reason,
                extra_data={"order_count": order_count, "same_item_only": same_item_only},
            )

        logger.info(
            f"{pf}[同用户已有订单规则] 通过：buyer_id={context.buyer_id}, "
            f"owner_id={context.owner_id}, 无其他订单"
        )
        return RuleCheckResult(
            hit=False,
            rule_code=self.rule_code,
            rule_name=self.rule_name,
            extra_data={"order_count": 0},
        )

    async def _count_owner_orders(
        self,
        owner_id: int,
        buyer_id: str,
        exclude_order_no: str,
        item_id: str | None = None,
    ) -> int:
        """查询买家在该用户名下所有账号中的其他订单数量

        Args:
            owner_id: 所属用户ID（覆盖该用户全部账号）
            buyer_id: 买家ID
            exclude_order_no: 排除当前订单号
            item_id: 如果指定，仅统计同商品订单

        Returns:
            其他订单数量
        """
        async with async_session_maker() as session:
            conditions = [
                XYOrder.owner_id == owner_id,
                XYOrder.buyer_id == buyer_id,
                XYOrder.order_no != exclude_order_no,
            ]
            if item_id:
                conditions.append(XYOrder.item_id == item_id)

            stmt = select(func.count(XYOrder.id)).where(and_(*conditions))
            result = await session.execute(stmt)
            return result.scalar() or 0
