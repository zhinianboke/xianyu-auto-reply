"""
充值订单模型

存储用户余额充值订单记录，包含订单号、金额、支付状态、支付宝交易号等信息
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class RechargeOrder(Base):
    """充值订单表"""

    __tablename__ = "xy_recharge_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    order_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment='充值订单号')
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment='用户ID')
    amount: Mapped[str] = mapped_column(String(32), nullable=False, comment='充值金额')
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default='pending', server_default='pending',
        comment='订单状态：pending-待支付，paid-已支付，expired-已过期，failed-失败'
    )
    trade_no: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment='支付宝交易号')
    qr_code: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment='支付二维码内容')
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment='支付时间')
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment='创建时间'
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间'
    )
