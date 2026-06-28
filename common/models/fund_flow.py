"""
资金流水模型

存储用户的资金变动记录，包含发生额、余额变动、关联订单等信息
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class FundFlow(Base):
    """资金流水表"""

    __tablename__ = "xy_fund_flows"
    __table_args__ = (
        Index("idx_ff_user_id_desc", "user_id", "id"),
        Index("idx_ff_user_type_id_desc", "user_id", "type", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment='用户ID')
    type: Mapped[str] = mapped_column(String(32), nullable=False, comment='流水类型：income-收入，expense-支出')
    amount: Mapped[str] = mapped_column(String(32), nullable=False, comment='发生额')
    balance_before: Mapped[str] = mapped_column(String(32), nullable=False, comment='发生前余额')
    balance_after: Mapped[str] = mapped_column(String(32), nullable=False, comment='发生后余额')
    order_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment='关联订单ID')
    dock_record_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True, comment='关联对接记录ID')
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment='流水描述')
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment='发生时间'
    )
