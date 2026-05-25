"""
买家存在未确认收货订单规则

功能：
1. 查询本地订单表，检查同一买家在同一卖家下是否有未确认收货的订单
2. 未确认收货订单数 >= 阈值时命中拦截
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

# 未确认收货的订单状态列表（已发货但买家未确认收货）
UNCONFIRMED_STATUSES = ("shipped",)


class BuyerUnconfirmedRule(BaseDeliveryRule):
    """买家存在未确认收货订单规则：同一买家有未确认收货订单时拦截"""

    @property
    def rule_code(self) -> str:
        return "buyer_unconfirmed"

    @property
    def rule_name(self) -> str:
        return "买家存在未确认收货订单"

    @property
    def rule_description(self) -> str:
        return "检查买家在当前卖家下是否有未确认收货的订单，有则禁止发货"

    @property
    def default_config(self) -> dict:
        # min_count: 未确认收货订单数达到多少时触发拦截
        # same_item_only: 是否仅限同商品订单才算命中
        return {"min_count": 1, "same_item_only": False}

    async def check(self, context: DeliveryCheckContext) -> RuleCheckResult:
        """检查买家是否有未确认收货订单"""
        pf = context.log_prefix or f"【{context.cookie_id}】"
        min_count = context.rule_config.get("min_count", 1)
        same_item_only = context.rule_config.get("same_item_only", False)

        try:
            unconfirmed_count = await self._count_unconfirmed_orders(
                account_id=context.cookie_id,
                buyer_id=context.buyer_id,
                exclude_order_no=context.order_no,
                item_id=context.item_id if same_item_only else None,
            )
        except Exception as e:
            logger.error(f"{pf}[未确认收货规则] 查询异常: {e}")
            # 查询异常不拦截，放行
            return RuleCheckResult(
                hit=False,
                rule_code=self.rule_code,
                rule_name=self.rule_name,
            )

        if unconfirmed_count >= min_count:
            reason = f"买家有{unconfirmed_count}笔未确认收货订单，禁止发货"
            logger.info(
                f"{pf}[未确认收货规则] 命中：buyer_id={context.buyer_id}, "
                f"unconfirmed_count={unconfirmed_count}, min_count={min_count}"
            )
            return RuleCheckResult(
                hit=True,
                rule_code=self.rule_code,
                rule_name=self.rule_name,
                reason=reason,
                extra_data={"unconfirmed_count": unconfirmed_count, "min_count": min_count},
            )

        logger.info(
            f"{pf}[未确认收货规则] 通过：buyer_id={context.buyer_id}, "
            f"unconfirmed_count={unconfirmed_count}, min_count={min_count}"
        )
        return RuleCheckResult(
            hit=False,
            rule_code=self.rule_code,
            rule_name=self.rule_name,
            extra_data={"unconfirmed_count": unconfirmed_count},
        )

    async def _count_unconfirmed_orders(
        self,
        account_id: str,
        buyer_id: str,
        exclude_order_no: str,
        item_id: str | None = None,
    ) -> int:
        """查询买家在该卖家下的未确认收货订单数量

        Args:
            account_id: 卖家账号标识
            buyer_id: 买家ID
            exclude_order_no: 排除当前订单号
            item_id: 如果指定，仅统计同商品订单

        Returns:
            未确认收货订单数量
        """
        async with async_session_maker() as session:
            conditions = [
                XYOrder.account_id == account_id,
                XYOrder.buyer_id == buyer_id,
                XYOrder.order_no != exclude_order_no,
                XYOrder.status.in_(UNCONFIRMED_STATUSES),
            ]
            if item_id:
                conditions.append(XYOrder.item_id == item_id)

            stmt = select(func.count(XYOrder.id)).where(and_(*conditions))
            result = await session.execute(stmt)
            return result.scalar() or 0
