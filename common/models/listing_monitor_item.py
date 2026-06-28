"""
商品监控采集商品信息模型

功能：
1. 定义采集商品信息表结构（xy_listing_monitor_items）
2. 与商品监控任务（xy_listing_monitor_tasks）关联，记录每次采集到的商品
3. 通过 (monitor_task_id, item_id) 唯一约束区分新增与更新
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ListingMonitorItem(TimestampMixin, Base):
    """商品监控采集商品信息表"""

    __tablename__ = "xy_listing_monitor_items"
    __table_args__ = (
        UniqueConstraint("monitor_task_id", "item_id", name="uk_lmi_task_item"),
        Index("idx_lmi_task", "monitor_task_id"),
        Index("idx_lmi_owner", "owner_id"),
        Index("idx_lmi_publish_time", "publish_time"),
        Index("idx_lmi_created", "created_at"),
        # 「采集商品发送私信」定时任务：order_status='success' + is_dm_sent=0 + ordered_at>=cutoff
        Index("idx_lmi_dm_send", "order_status", "is_dm_sent", "ordered_at"),
        # 「采集商品自动下单」定时任务：is_ordered=0 + order_attempts<上限
        Index("idx_lmi_order_pending", "is_ordered", "order_attempts"),
        # 下单去重 has_owner_ordered_item：按 item_id + is_ordered 查（item_id 原仅为联合唯一键非最左列）
        Index("idx_lmi_item_ordered", "item_id", "is_ordered"),
        # 前端列表分页：owner_id 过滤 + 按 publish_time 排序
        Index("idx_lmi_owner_publish", "owner_id", "publish_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    monitor_task_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="关联的商品监控任务ID")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, comment="归属用户ID")
    item_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="闲鱼商品ID")
    title: Mapped[str | None] = mapped_column(String(500), comment="商品标题")
    price: Mapped[str | None] = mapped_column(String(32), comment="商品价格（展示文本）")
    area: Mapped[str | None] = mapped_column(String(120), comment="商品所在地区")
    pic_url: Mapped[str | None] = mapped_column(String(1000), comment="商品主图URL")
    seller_id: Mapped[str | None] = mapped_column(String(120), comment="卖家ID（搜索返回，可能为加密串）")
    seller_user_id: Mapped[str | None] = mapped_column(String(64), comment="卖家真实用户ID（商品详情接口补全）")
    seller_nick: Mapped[str | None] = mapped_column(String(120), comment="卖家昵称")
    seller_avatar: Mapped[str | None] = mapped_column(String(1000), comment="卖家头像URL")
    want_count: Mapped[str | None] = mapped_column(String(32), comment="想要数（从营销标签解析的真实想要人数）")
    tags: Mapped[str | None] = mapped_column(String(500), comment="商品营销标签（逗号分隔，如：4天内上新,235人想要）")
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="商品发布时间")
    target_url: Mapped[str | None] = mapped_column(String(1000), comment="商品详情跳转URL")
    raw_json: Mapped[str | None] = mapped_column(Text, comment="商品原始数据（搜索结果项JSON，兜底）")
    detail_json: Mapped[str | None] = mapped_column(Text, comment="商品详情数据（详情接口返回JSON）")
    seller_fill_status: Mapped[str | None] = mapped_column(String(20), comment="卖家ID补全结果：failed-明确失败不再补全（如跨境商品/已下架）")
    seller_fill_fail_reason: Mapped[str | None] = mapped_column(String(500), comment="卖家ID补全失败原因（明确业务失败的原文）")
    is_dm_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0", comment="是否已发起私信（已处理，避免重复发送）")
    dm_account_id: Mapped[str | None] = mapped_column(String(80), comment="成功私信使用的账号ID（后续优先用该账号下单）")
    dm_chat_id: Mapped[str | None] = mapped_column(String(80), comment="私信会话ID（create-chat 返回的 chat_id）")
    dm_status: Mapped[str | None] = mapped_column(String(20), comment="私信发送结果：success-成功，failed-失败(被拦截)，unknown-未确认")
    dm_fail_reason: Mapped[str | None] = mapped_column(String(500), comment="私信发送失败原因（如安全拦截文案）")
    dm_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="私信发送尝试次数（失败重试用，达上限后不再重试）")
    is_ordered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0", comment="是否已下单成功")
    order_id: Mapped[str | None] = mapped_column(String(64), comment="下单成功的订单ID（拍下）")
    order_account_id: Mapped[str | None] = mapped_column(String(80), comment="下单成功使用的账号ID（发起私信时严格使用该账号）")
    order_status: Mapped[str | None] = mapped_column(String(20), comment="下单结果：success-成功，failed-失败")
    order_fail_reason: Mapped[str | None] = mapped_column(String(500), comment="下单失败原因")
    order_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="下单尝试次数（失败重试用，达上限后不再重试）")
    dm_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="实际私信成功/发起时间（用于按日统计私信数）")
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="下单成功时间（用于按日统计下单数）")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最近一次采集到的时间")
