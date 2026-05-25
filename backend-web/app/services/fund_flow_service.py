"""
资金流水服务

提供资金流水的查询功能
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from common.models.fund_flow import FundFlow
from common.utils.pagination import (
    build_pagination_response,
    execute_paginated_with_filters,
)
from common.utils.time_utils import safe_isoformat


class FundFlowService:
    """资金流水服务类"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_fund_flows_paginated(
        self,
        user_id: Optional[int] = None,
        flow_type: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """分页获取资金流水列表
        
        Args:
            user_id: 用户ID，None表示查询所有（管理员）
            flow_type: 流水类型筛选（income/expense），空字符串表示全部
            page: 页码
            page_size: 每页数量
            
        Returns:
            分页数据字典
        """
        # 收集过滤条件交由公共分页工具同时应用到 list 与 count
        filters: list = []
        if user_id is not None:
            filters.append(FundFlow.user_id == user_id)
        if flow_type:
            filters.append(FundFlow.type == flow_type)

        flows, total = await execute_paginated_with_filters(
            self.session,
            FundFlow,
            filters=filters,
            order_by=[FundFlow.id.desc()],
            page=page,
            page_size=page_size,
        )

        return build_pagination_response(
            [self._flow_to_dict(f) for f in flows],
            total,
            page,
            page_size,
        )

    def _flow_to_dict(self, flow: FundFlow) -> Dict[str, Any]:
        """将资金流水记录转换为字典"""
        return {
            "id": flow.id,
            "user_id": flow.user_id,
            "type": flow.type,
            "amount": flow.amount,
            "balance_before": flow.balance_before,
            "balance_after": flow.balance_after,
            "order_id": flow.order_id,
            "dock_record_id": flow.dock_record_id,
            "description": flow.description,
            "created_at": safe_isoformat(flow.created_at),
        }
