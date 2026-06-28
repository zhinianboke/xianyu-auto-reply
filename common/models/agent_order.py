"""
代理订单模型

功能：
1. 记录通过对接卡券发货产生的代理订单
2. 包含售价、发货内容、对接层级、利润分配等信息
3. 用于后续利润结算和手续费扣除
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class AgentOrder(Base):
    """代理订单表 - 记录对接卡券发货产生的订单"""

    __tablename__ = "xy_agent_orders"
    __table_args__ = (
        Index("idx_agent_order_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment='下单用户ID（发货方）')
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment='闲鱼订单号')
    item_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='商品ID')
    card_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment='使用的卡券ID')
    dock_record_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment='对接记录ID')
    dock_level: Mapped[int] = mapped_column(Integer, nullable=False, comment='对接层级：1=一级，2=二级')

    # 价格信息
    sale_price: Mapped[str] = mapped_column(String(32), nullable=False, comment='售价（用户卖出的价格）')
    dock_price: Mapped[str] = mapped_column(String(32), nullable=False, comment='对接价格（拿货价）')
    card_price: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment='卡券成本（货主对接价）')
    level2_cost: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment='二级拿货价（一级的sub_dock_price）')
    profit: Mapped[str] = mapped_column(String(32), nullable=False, default='0.00', comment='利润（售价-对接价）')
    fee_amount: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment='手续费金额')
    fee_payer: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment='手续费承担方：dealer-分销商，distributor-货主')

    # 上级信息
    upstream_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment='上级用户ID（卡券拥有者/一级分销商）')
    upstream_dock_record_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment='上级对接记录ID（二级对接时的一级记录）')
    owner_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment='货主用户ID')

    # 发货信息
    delivery_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment='发货内容')
    buyer_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='买家ID')

    # 状态
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='delivered', comment='状态：delivered-已发货，settled-已结算，failed-失败')
    settle_remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment='结算备注')

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment='创建时间'
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间'
    )
