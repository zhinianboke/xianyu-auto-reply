"""
闲鱼账号模型

功能：
1. 定义闲鱼账号表结构（xy_accounts）
2. 存储账号Cookie、登录方式、状态等信息
3. 支持代理配置（HTTP/SOCKS5）
4. 关联关系：用户、关键词规则、商品目录、商品回复
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base_class import Base, TimestampMixin


class XYAccount(TimestampMixin, Base):
    """闲鱼账号表"""

    __tablename__ = "xy_accounts"
    __table_args__ = (
        Index("idx_account_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    unb: Mapped[str | None] = mapped_column(String(64), index=True)
    cookie: Mapped[str] = mapped_column(Text, nullable=False)
    login_method: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    username: Mapped[str | None] = mapped_column(String(120))
    login_password: Mapped[str | None] = mapped_column(Text)
    remark: Mapped[str | None] = mapped_column(String(255))
    pause_duration: Mapped[int] = mapped_column(Integer, default=10)
    auto_confirm: Mapped[bool] = mapped_column(Boolean, default=False)
    show_browser: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    
    # 代理配置字段
    proxy_type: Mapped[str | None] = mapped_column(String(20), default="none")
    proxy_host: Mapped[str | None] = mapped_column(String(255))
    proxy_port: Mapped[int | None] = mapped_column(Integer)
    proxy_user: Mapped[str | None] = mapped_column(String(120))
    proxy_pass: Mapped[str | None] = mapped_column(String(255))
    
    # 相同消息等待时间(秒)
    message_expire_time: Mapped[int] = mapped_column(Integer, default=3600)
    
    # 禁用原因
    disable_reason: Mapped[str | None] = mapped_column(String(255))
    
    # 定时补发货开关
    scheduled_redelivery: Mapped[bool] = mapped_column(Boolean, default=False, comment="定时补发货开关")
    
    # 定时补评价开关
    scheduled_rate: Mapped[bool] = mapped_column(Boolean, default=False, comment="定时补评价开关")
    
    # 商品自动擦亮开关
    auto_polish: Mapped[bool] = mapped_column(Boolean, default=False, comment="商品自动擦亮开关")
    
    # 发货成功再发卡券开关（开启后确认发货失败则不发送卡券）
    confirm_before_send: Mapped[bool] = mapped_column(Boolean, default=False, comment="发货成功再发卡券开关")
    
    # 卡券发送成功再确认发货开关（与confirm_before_send互斥，开启后先发卡券再确认发货）
    send_before_confirm: Mapped[bool] = mapped_column(Boolean, default=False, comment="卡券发送成功再确认发货开关")
    
    # 自动求小红花开关
    auto_red_flower: Mapped[bool] = mapped_column(Boolean, default=False, comment="自动求小红花开关")

    # 禁止发货开关（仅做配置存储，发货逻辑后续接入）
    delivery_disabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="禁止发货开关")

    # 禁止发货原因
    delivery_disabled_reason: Mapped[str | None] = mapped_column(String(500), comment="禁止发货原因")

    # 主动关闭订单开关（命中禁止发货时是否调用闲鱼接口主动关闭订单）
    auto_close_order: Mapped[bool] = mapped_column(Boolean, default=False, comment="主动关闭订单开关")

    # 关闭订单后继续发货开关（仅在 auto_close_order=True 且关闭成功后生效）
    # 开启时：跳过确认发货接口和免拼接口，直接向买家发送卡券内容；关闭时：维持原拦截逻辑（不发任何内容）
    delivery_only_card_after_close: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="关闭订单后继续发货（只发卡券，不调发货/免拼接口）"
    )

    # 禁止发货排除商品列表（JSON 列表存储 item_id）
    # 当订单的 item_id 命中本列表时，跳过禁止发货拦截，按正常流程发货
    # 仅在 delivery_disabled=True 时生效；列表为空或 None 表示不排除任何商品
    delivery_disabled_excluded_items: Mapped[list[str] | None] = mapped_column(
        JSON, comment="禁止发货排除商品列表（item_id 数组，命中后按正常流程发货）"
    )

    # 已下单用户禁止AI回复开关
    # 开启后：对已在订单表中有订单记录的买家，跳过AI回复，使用关键词或默认回复
    ai_reply_block_ordered_users: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="已下单用户禁止AI回复"
    )

    # 关系定义 - 无外键约束
    owner: Mapped["User"] = relationship(
        "User",
        primaryjoin="XYAccount.owner_id == User.id",
        foreign_keys="[XYAccount.owner_id]",
        back_populates="accounts",
        viewonly=True,
    )
    keyword_rules: Mapped[list["XYKeywordRule"]] = relationship(
        "XYKeywordRule",
        primaryjoin="XYAccount.id == XYKeywordRule.account_pk",
        foreign_keys="XYKeywordRule.account_pk",
        back_populates="account",
        viewonly=True,
    )
    catalog_items: Mapped[list["XYCatalogItem"]] = relationship(
        "XYCatalogItem",
        primaryjoin="XYAccount.id == XYCatalogItem.account_pk",
        foreign_keys="XYCatalogItem.account_pk",
        back_populates="account",
        viewonly=True,
    )

