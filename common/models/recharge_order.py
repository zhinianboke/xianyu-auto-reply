"""
充值订单模型

存储余额充值和广告付款订单，包含支付渠道、支付目标、状态及上游交易号等信息
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class RechargeOrder(Base):
    """充值订单表"""

    __tablename__ = "xy_recharge_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    order_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment='充值订单号')
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment='用户ID')
    amount: Mapped[str] = mapped_column(String(32), nullable=False, comment='充值金额')
    # 订单类型：recharge-余额充值，ad-广告申请付款。
    # 该表被充值和广告付款共用，且共用同一个支付宝异步回调，必须靠此字段区分处理逻辑，
    # 避免广告付款被当成充值给用户加余额（历史 bug）。
    order_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default='recharge', server_default='recharge',
        comment='订单类型：recharge-余额充值，ad-广告申请付款'
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default='alipay', server_default='alipay',
        comment='支付渠道：alipay-支付宝当面付，zzcode-码支付'
    )
    pay_type: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, comment='码支付子方式：alipay/wxpay/qqpay'
    )
    zzcode_amount_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
        comment='码支付订单金额是否已确认'
    )
    callback_merchant_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment='创建订单时使用的回调验签商户ID'
    )
    callback_verify_key: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment='创建订单时使用的回调验签密钥或公钥'
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default='pending', server_default='pending',
        comment='订单状态：pending-待支付，paid-已支付，expired-已过期，failed-失败'
    )
    trade_no: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment='上游支付交易号')
    qr_code: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment='支付二维码内容')
    pay_target_kind: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, comment='支付目标类型：qrcode/payurl/urlscheme'
    )
    pay_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, comment='支付跳转或协议链接')
    ad_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment='广告付款关联广告ID')
    ad_settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment='广告付款结算时间')
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment='支付时间')
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment='创建时间'
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间'
    )
