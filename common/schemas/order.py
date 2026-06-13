from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OrderOut(BaseModel):
    id: str
    order_id: str
    cookie_id: str | None = None
    item_id: str | None = None
    item_title: str | None = None  # 商品标题
    buyer_id: str | None = None
    buyer_fish_nick: str | None = None  # 买家闲鱼昵称（明文）
    chat_id: str | None = None  # 聊天会话ID
    sku_info: str | None = None
    quantity: int
    amount: str
    status: str
    is_bargain: bool = False  # 是否小刀
    is_rated: bool = False  # 是否已评价
    is_red_flower: bool = False  # 是否已求小红花
    # 收货人信息
    receiver_name: str | None = None  # 收货人姓名
    receiver_phone: str | None = None  # 收货人手机号
    receiver_address: str | None = None  # 收货地址
    # 发货信息
    delivery_method: str | None = None  # 发货方式：manual-手动发货, auto-自动发货, scheduled-定时发货
    delivery_content: str | None = None  # 发货内容（卡券内容）
    delivery_fail_reason: str | None = None  # 发货失败原因
    # 关联自动发货消息日志的发送状态
    delivery_send_status: str | None = None  # 消息日志发送状态：success/failed/unknown/timeout
    delivery_send_fail_reason: str | None = None  # 消息日志发送失败原因
    is_agent_order: bool = False  # 是否是代销订单
    source: str | None = None  # 数据来源
    placed_at: datetime | None = None  # 订单时间（下单时间）
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OrderListResponse(BaseModel):
    success: bool = True
    data: list[OrderOut]

