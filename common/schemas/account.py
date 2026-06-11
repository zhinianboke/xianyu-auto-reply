"""
账号相关Schema定义

功能：
1. 定义账号详情格式（AccountDetail）
2. 定义账号创建和更新请求格式
3. 兼容旧版API的数据结构
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AccountDetail(BaseModel):
    """账号详情 - 兼容旧版API的数据结构"""

    pk: int  # 数据库主键
    id: str
    value: str
    enabled: bool
    auto_confirm: bool
    scheduled_redelivery: bool = False
    scheduled_rate: bool = False
    auto_polish: bool = False
    confirm_before_send: bool = False
    send_before_confirm: bool = False
    auto_red_flower: bool = False
    ai_reply_block_ordered_users: bool = False
    delivery_disabled: bool = False
    delivery_disabled_reason: str | None = None
    auto_close_order: bool = False
    delivery_only_card_after_close: bool = False
    delivery_disabled_excluded_item_ids: list[str] = Field(
        default_factory=list,
        description="禁止发货排除商品列表（命中此列表的 item_id 不受禁止发货拦截）",
    )
    remark: str | None = None
    pause_duration: int | None = None
    message_expire_time: int | None = None
    reply_delay_seconds: int | None = None
    username: str | None = None
    login_password: str | None = None
    show_browser: bool = False
    disable_reason: str | None = None
    filter_count: int = 0  # 消息过滤规则数量


class AccountOption(BaseModel):
    """账号下拉选项"""

    pk: int
    id: str
    remark: str | None = None
    enabled: bool = True
    show_browser: bool = False


class AccountCreate(BaseModel):
    id: str = Field(..., description="Unique account identifier provided by the user")
    value: str = Field(..., description="Raw cookie content")


class AccountCookieUpdate(BaseModel):
    value: str = Field(..., description="Updated cookie text")


class AccountStatusUpdate(BaseModel):
    enabled: bool


class AccountBatchIdsUpdate(BaseModel):
    account_ids: list[str]


class AccountBatchStatusUpdate(BaseModel):
    account_ids: list[str]
    enabled: bool


class AccountRemarkUpdate(BaseModel):
    remark: str


class AccountAutoConfirmUpdate(BaseModel):
    auto_confirm: bool


class AccountPauseDurationUpdate(BaseModel):
    pause_duration: int = Field(..., ge=0, le=3600)


class AccountLoginInfoUpdate(BaseModel):
    """账号登录信息更新"""
    username: str | None = Field(None, description="登录用户名")
    login_password: str | None = Field(None, description="登录密码")
    show_browser: bool | None = Field(None, description="是否显示浏览器")


class AccountMessageExpireTimeUpdate(BaseModel):
    """相同消息等待时间更新"""
    message_expire_time: int = Field(..., ge=0, le=86400, description="相同消息等待时间(秒)，范围0-86400，0表示不限制")


class AccountReplyDelayUpdate(BaseModel):
    """自动回复延迟时间更新"""
    reply_delay_seconds: int = Field(..., ge=0, le=3600, description="自动回复延迟时间(秒)，范围0-3600，0表示立即回复")


class AccountScheduledRedeliveryUpdate(BaseModel):
    """定时补发货开关更新"""
    scheduled_redelivery: bool = Field(..., description="定时补发货开关")


class AccountScheduledRateUpdate(BaseModel):
    """定时补评价开关更新"""
    scheduled_rate: bool = Field(..., description="定时补评价开关")



class AccountAutoPolishUpdate(BaseModel):
    """商品自动擦亮开关更新"""
    auto_polish: bool = Field(..., description="商品自动擦亮开关")


class AccountConfirmBeforeSendUpdate(BaseModel):
    """发货成功再发卡券开关更新"""
    confirm_before_send: bool = Field(..., description="发货成功再发卡券开关")


class AccountSendBeforeConfirmUpdate(BaseModel):
    """卡券发送成功再确认发货开关更新"""
    send_before_confirm: bool = Field(..., description="卡券发送成功再确认发货开关")


class AccountAutoRedFlowerUpdate(BaseModel):
    """自动求小红花开关更新"""
    auto_red_flower: bool = Field(..., description="自动求小红花开关")


class AccountAiReplyBlockOrderedUsersUpdate(BaseModel):
    """已下单用户禁止AI回复开关更新"""
    ai_reply_block_ordered_users: bool = Field(..., description="已下单用户禁止AI回复开关")


class AccountDeliveryDisabledUpdate(BaseModel):
    """禁止发货设置更新（已废弃，保留向后兼容）"""
    delivery_disabled: bool = Field(..., description="禁止发货开关")
    delivery_disabled_reason: str | None = Field(
        default=None,
        max_length=500,
        description="禁止发货原因",
    )
    auto_close_order: bool = Field(
        default=False,
        description="命中禁止发货时是否主动关闭订单",
    )
    delivery_only_card_after_close: bool = Field(
        default=False,
        description="关闭订单后继续发货（仅发卡券，不调发货/免拼接口）。仅在 auto_close_order=True 时生效",
    )
    excluded_item_ids: list[str] = Field(
        default_factory=list,
        description="禁止发货排除商品列表（命中此列表的 item_id 跳过禁止发货拦截，按正常流程发货）",
    )


class DeliveryBlockRuleItem(BaseModel):
    """单条禁止发货规则配置"""
    rule_code: str = Field(..., description="规则编码")
    enabled: bool = Field(default=False, description="规则开关")
    priority: int = Field(default=0, description="执行优先级（越小越先执行）")
    block_reason: str | None = Field(
        default=None,
        max_length=500,
        description="禁止发货原因（发给买家的消息）",
    )
    auto_close_order: bool = Field(
        default=False,
        description="命中后主动关闭订单",
    )
    only_card_after_close: bool = Field(
        default=False,
        description="关闭订单后继续发货（只发卡券）",
    )
    excluded_item_ids: list[str] = Field(
        default_factory=list,
        description="该规则的排除商品列表（命中则跳过本规则）",
    )
    config: dict | None = Field(
        default=None,
        description="规则专属参数",
    )


class DeliveryBlockRulesUpdate(BaseModel):
    """禁止发货规则批量更新"""
    rules: list[DeliveryBlockRuleItem] = Field(
        ...,
        description="规则配置列表",
    )
