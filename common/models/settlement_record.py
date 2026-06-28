"""结算记录模型"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class SettlementRecord(Base):
    """用户结算记录表"""

    __tablename__ = "xy_settlement_records"
    __table_args__ = (
        Index("idx_sr_user_created_id", "user_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment='用户ID')
    alipay_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment='支付宝ID（兼容旧数据）')
    payment_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, comment='收款方式：alipay-支付宝，wechat-微信')
    payment_qrcode: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment='收款码图片路径')
    amount: Mapped[str] = mapped_column(String(32), nullable=False, comment='提现金额')
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='pending_review', comment='状态：pending_review-待审核，approved-已通过，rejected-已拒绝，paid-已打款')
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment='备注')
    reject_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment='拒绝原因')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False, comment='创建时间')
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False, comment='更新时间')
