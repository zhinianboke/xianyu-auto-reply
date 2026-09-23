"""
资金流水服务

提供资金流水的查询功能
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.fund_flow import FundFlow
from common.models.user import User
from common.utils.pagination import build_pagination_response
from common.utils.time_utils import safe_isoformat


class FundFlowService:
    """资金流水服务类"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_fund_flows_paginated(
        self,
        user_id: Optional[int] = None,
        flow_type: str = "",
        username: str = "",
        page: int = 1,
        page_size: int = 20,
        description: str = "",
    ) -> Dict[str, Any]:
        """分页获取资金流水列表（关联用户名）

        通过 LEFT JOIN 用户表取出每笔流水对应的用户名，避免用户被软删除后
        流水记录丢失。支持按描述模糊筛选，管理员还可按用户名筛选。

        Args:
            user_id: 用户ID，None表示查询所有（管理员）
            flow_type: 流水类型筛选（income/expense/fee），空字符串表示全部
            username: 用户名模糊筛选，空字符串表示不筛选
            page: 页码
            page_size: 每页数量
            description: 流水描述模糊筛选，空字符串表示不筛选

        Returns:
            分页数据字典
        """
        # 收集过滤条件，统一应用到 list 与 count 两条语句
        conditions: list = []
        if user_id is not None:
            conditions.append(FundFlow.user_id == user_id)
        if flow_type:
            conditions.append(FundFlow.type == flow_type)
        if username:
            # 参数化模糊查询，防 SQL 注入
            conditions.append(User.username.like(f"%{username.strip()}%"))
        if description.strip():
            # autoescape 会转义用户输入中的 LIKE 通配符，同时保持参数化查询
            conditions.append(
                FundFlow.description.contains(description.strip(), autoescape=True)
            )

        # LEFT JOIN 用户表，同时取出流水与用户名
        list_stmt = select(FundFlow, User.username).outerjoin(
            User, User.id == FundFlow.user_id
        )
        count_stmt = (
            select(func.count())
            .select_from(FundFlow)
            .outerjoin(User, User.id == FundFlow.user_id)
        )
        if conditions:
            list_stmt = list_stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        list_stmt = (
            list_stmt.order_by(FundFlow.id.desc())
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
        )

        total = (await self.session.execute(count_stmt)).scalar() or 0
        rows = (await self.session.execute(list_stmt)).all()
        items = [self._flow_to_dict(flow, uname) for flow, uname in rows]

        return build_pagination_response(items, int(total), page, page_size)

    def _flow_to_dict(self, flow: FundFlow, username: Optional[str] = None) -> Dict[str, Any]:
        """将资金流水记录转换为字典

        Args:
            flow: 资金流水 ORM 对象
            username: 关联的用户名（用户被删除时为 None）
        Returns:
            资金流水字典
        """
        return {
            "id": flow.id,
            "user_id": flow.user_id,
            "username": username,
            "type": flow.type,
            "amount": flow.amount,
            "balance_before": flow.balance_before,
            "balance_after": flow.balance_after,
            "order_id": flow.order_id,
            "dock_record_id": flow.dock_record_id,
            "description": flow.description,
            "created_at": safe_isoformat(flow.created_at),
        }
