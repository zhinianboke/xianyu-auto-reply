"""
订单模型

功能：
1. 定义订单表结构（xy_orders）
2. 存储从闲鱼同步的订单信息
3. 包含买家信息、商品信息、金额、收货人信息等
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class XYOrder(TimestampMixin, Base):
    """订单表 - 存储从闲鱼同步的订单信息"""

    __tablename__ = "xy_orders"
    __table_args__ = (
        Index("idx_order_created_at", "created_at"),
        Index("idx_order_placed_status", "placed_at", "status"),
        Index("idx_order_created_status", "created_at", "status"),
        Index("idx_order_owner_placed", "owner_id", "placed_at"),
        Index("idx_order_owner_created", "owner_id", "created_at"),
        Index("idx_order_owner_account_placed", "owner_id", "account_id", "placed_at"),
        Index("idx_order_owner_account_buyer_created", "owner_id", "account_id", "buyer_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="订单ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="所属用户ID")
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="订单号")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="订单状态")
    buyer_nick: Mapped[str | None] = mapped_column(String(120), comment="买家昵称")
    buyer_fish_nick: Mapped[str | None] = mapped_column(String(120), comment="买家闲鱼昵称（明文）")
    buyer_id: Mapped[str | None] = mapped_column(String(64), comment="买家ID")
    chat_id: Mapped[str | None] = mapped_column(String(64), comment="聊天会话ID")
    item_id: Mapped[str | None] = mapped_column(String(64), comment="商品ID")
    spec_name: Mapped[str | None] = mapped_column(String(120), comment="规格名称")
    spec_value: Mapped[str | None] = mapped_column(String(120), comment="规格值")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="数量")
    amount: Mapped[Numeric | None] = mapped_column(Numeric(12, 2), comment="金额")
    currency: Mapped[str] = mapped_column(String(8), default="CNY", comment="货币")
    account_id: Mapped[str | None] = mapped_column(String(64), index=True, comment="账号标识")
    account_name: Mapped[str | None] = mapped_column(String(120), comment="账号名称")
    is_bargain: Mapped[bool] = mapped_column("is_bargain", default=False, comment="是否小刀")
    # 收货人信息
    receiver_name: Mapped[str | None] = mapped_column(String(120), comment="收货人姓名")
    receiver_phone: Mapped[str | None] = mapped_column(String(32), comment="收货人手机号")
    receiver_address: Mapped[str | None] = mapped_column(String(512), comment="收货地址")
    is_rated: Mapped[bool] = mapped_column("is_rated", default=False, comment="是否已评价")
    is_red_flower: Mapped[bool] = mapped_column("is_red_flower", default=False, comment="是否已求小红花")
    is_unregistered: Mapped[bool] = mapped_column("is_unregistered", default=False, comment="是否已请求注销接口")
    unregister_error_reason: Mapped[str | None] = mapped_column(String(500), comment="注销接口错误原因")
    # 发货信息
    delivery_method: Mapped[str | None] = mapped_column(String(32), comment="发货方式：manual-手动发货, auto-自动发货, scheduled-定时发货")
    delivery_content: Mapped[str | None] = mapped_column(String(2000), comment="发货内容（卡券内容）")
    delivery_fail_reason: Mapped[str | None] = mapped_column(String(2000), comment="发货失败原因")
    # 账号开启“只发卡券”时，平台状态仍可能是待发货；内容一旦取出即标记，防止重复耗卡。
    # 若消息发送失败，卡券内容会保存在 delivery_content 中并记录失败原因，交由人工补发。
    card_only_delivered: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="仅发卡券流程是否已处理"
    )
    # 同意后发货：买家在公开提货页点击「同意」的记录。点击后才触发免拼/确认发货并取卡展示。
    agree_deliver_agreed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="同意后发货-买家是否已点击同意"
    )
    agree_deliver_agreed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="同意后发货-买家点击同意时间"
    )
    item_snapshot: Mapped[dict | None] = mapped_column(JSON, comment="商品快照")
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, comment="元数据")
    source: Mapped[str | None] = mapped_column(String(32), comment="数据来源：fetch_xianyu-获取闲鱼订单按钮")
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="下单时间")
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="同步时间")

