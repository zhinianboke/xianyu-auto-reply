"""
自动回复消息日志模型

功能：
1. 定义自动回复消息日志表结构（xy_auto_reply_message_logs）
2. 记录自动回复消息的处理上下文、决策结果和发送结果
3. 便于按账号、会话、用户和策略追踪自动回复行为
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class XYAutoReplyMessageLog(Base):
    """自动回复消息日志表"""

    __tablename__ = "xy_auto_reply_message_logs"
    __table_args__ = (
        Index("idx_arml_account_created", "account_id", "created_at"),
        Index("idx_arml_account_status_created", "account_id", "process_status", "created_at"),
        Index("idx_arml_owner_created", "owner_id", "created_at"),
        Index("idx_arml_owner_status_created", "owner_id", "process_status", "created_at"),
        Index("idx_arml_status_created", "process_status", "created_at"),
        Index("idx_arml_status_strategy_created", "process_status", "reply_strategy", "created_at"),
        Index("idx_arml_strategy_created", "reply_strategy", "created_at"),
        Index("idx_arml_order_strategy_id", "order_no", "reply_strategy", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="所属系统用户ID")
    owner_username: Mapped[str | None] = mapped_column(String(120), comment="所属系统用户名")
    account_pk: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="账号主键ID")
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True, comment="闲鱼账号ID")
    account_name: Mapped[str | None] = mapped_column(String(120), comment="闲鱼账号显示名称")
    chat_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True, comment="聊天会话ID")
    item_id: Mapped[str | None] = mapped_column(String(64), index=True, comment="商品ID")
    item_title: Mapped[str | None] = mapped_column(String(255), comment="商品标题")
    order_no: Mapped[str | None] = mapped_column(String(64), index=True, comment="订单号（自动发货等场景关联订单）")
    source_message_id: Mapped[str | None] = mapped_column(String(128), index=True, comment="源消息ID")
    sender_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="发送方闲鱼用户ID")
    sender_user_name: Mapped[str | None] = mapped_column(String(120), comment="发送方昵称")
    source_message: Mapped[str | None] = mapped_column(Text, comment="收到的消息内容")
    source_message_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="收到消息时间")
    process_status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing", index=True, comment="处理状态：processing/success/skipped/failed")
    decision_reason: Mapped[str] = mapped_column(String(64), nullable=False, default="processing", index=True, comment="决策原因")
    reply_strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="none", comment="回复策略：keyword/ai/default/none")
    reply_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="none", comment="回复模式：text/image/text_image/none")
    matched_keyword: Mapped[str | None] = mapped_column(String(255), comment="命中的关键词")
    matched_rule_type: Mapped[str | None] = mapped_column(String(32), comment="命中的规则类型")
    default_reply_scope: Mapped[str | None] = mapped_column(String(20), comment="默认回复作用域：item/account")
    default_reply_once: Mapped[bool] = mapped_column(Boolean, default=False, comment="默认回复是否仅回复一次")
    ai_model_name: Mapped[str | None] = mapped_column(String(120), comment="AI模型名称")
    ai_provider_name: Mapped[str | None] = mapped_column(String(80), comment="AI服务商名称")
    reply_text: Mapped[str | None] = mapped_column(Text, comment="回复文本内容")
    reply_image_url: Mapped[str | None] = mapped_column(String(1000), comment="回复图片URL")
    reply_segments: Mapped[list | None] = mapped_column(JSON, comment="拆分后的回复分段")
    error_message: Mapped[str | None] = mapped_column(Text, comment="错误信息")
    send_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown", comment="发送状态：success-发送成功/failed-发送失败/unknown-未知(无响应)/timeout-超时(无响应超过阈值)")
    send_fail_reason: Mapped[str | None] = mapped_column(Text, comment="发送失败原因（如被安全拦截的明文文案）")
    raw_message_json: Mapped[dict | None] = mapped_column(JSON, comment="原始消息JSON")
    context_snapshot: Mapped[dict | None] = mapped_column(JSON, comment="上下文快照")
    send_result_json: Mapped[list | dict | None] = mapped_column(JSON, comment="发送结果快照")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
