"""
买家已有订单规则

功能：
1. 查询本地订单表，检查同一买家在同一卖家下是否已有其他订单
2. 存在其他订单时命中拦截
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


class BuyerHasOrderRule(BaseDeliveryRule):
    """买家已有订单规则：同一买家在同一卖家下已有其他订单时拦截"""

    @property
    def rule_code(self) -> str:
        return "buyer_has_order"

    @property
    def rule_name(self) -> str:
        return "买家已有订单"

    @property
    def rule_description(self) -> str:
        return "检查买家在当前卖家下是否已有其他订单，有则禁止发货"

    @property
    def default_config(self) -> dict:
        # same_item_only: 是否仅限同商品订单才算命中
        return {"same_item_only": False}

    async def check(self, context: DeliveryCheckContext) -> RuleCheckResult:
        """检查买家是否已有其他订单"""
        pf = context.log_prefix or f"【{context.cookie_id}】"
        same_item_only = context.rule_config.get("same_item_only", False)

        try:
            order_count = await self._count_buyer_orders(
                account_id=context.cookie_id,
                buyer_id=context.buyer_id,
                exclude_order_no=context.order_no,
                item_id=context.item_id if same_item_only else None,
            )
        except Exception as e:
            logger.error(f"{pf}[买家已有订单规则] 查询异常: {e}")
            # 查询异常不拦截，放行
            return RuleCheckResult(
                hit=False,
                rule_code=self.rule_code,
                rule_name=self.rule_name,
            )

        if order_count > 0:
            reason = f"买家已有{order_count}笔其他订单，禁止发货"
            logger.info(
                f"{pf}[买家已有订单规则] 命中：buyer_id={context.buyer_id}, "
                f"order_count={order_count}, same_item_only={same_item_only}"
            )
            return RuleCheckResult(
                hit=True,
                rule_code=self.rule_code,
                rule_name=self.rule_name,
                reason=reason,
                extra_data={"order_count": order_count, "same_item_only": same_item_only},
            )

        logger.info(
            f"{pf}[买家已有订单规则] 通过：buyer_id={context.buyer_id}, 无其他订单"
        )
        return RuleCheckResult(
            hit=False,
            rule_code=self.rule_code,
            rule_name=self.rule_name,
            extra_data={"order_count": 0},
        )

    async def _count_buyer_orders(
        self,
        account_id: str,
        buyer_id: str,
        exclude_order_no: str,
        item_id: str | None = None,
    ) -> int:
        """查询买家在该卖家下的其他订单数量

        Args:
            account_id: 卖家账号标识
            buyer_id: 买家ID
            exclude_order_no: 排除当前订单号
            item_id: 如果指定，仅统计同商品订单

        Returns:
            其他订单数量
        """
        async with async_session_maker() as session:
            conditions = [
                XYOrder.account_id == account_id,
                XYOrder.buyer_id == buyer_id,
                XYOrder.order_no != exclude_order_no,
            ]
            if item_id:
                conditions.append(XYOrder.item_id == item_id)

            stmt = select(func.count(XYOrder.id)).where(and_(*conditions))
            result = await session.execute(stmt)
            return result.scalar() or 0
