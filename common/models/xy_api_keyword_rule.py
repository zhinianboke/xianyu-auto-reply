"""API关键词配置模型，供自动回复执行API请求及可选的同步确认发货。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base
from common.utils.time_utils import get_beijing_now_naive

HTTP_METHOD_DICTIONARY = "api_keyword_http_method"
PARAMETER_DICTIONARY = "api_keyword_parameter"
TRIGGER_REASON_DICTIONARY = "api_keyword_trigger_reason"
HTTP_METHODS = ("GET", "POST")
PARAMETER_PLACEHOLDERS = {"item_id": "{item_id}", "message": "{message}", "actId": "{actId}"}


class XYApiKeywordRule(Base):
    """按用户和账号隔离的API关键词配置，不关联旧关键词匹配表。"""

    __tablename__ = "xy_api_keyword_rules"
    __table_args__ = (
        Index("uk_api_keyword_request", "request_id", unique=True),
        Index("idx_api_keyword_owner_page", "owner_id", "is_deleted", "id"),
        Index("idx_api_keyword_account_page", "account_id", "is_deleted", "id"),
        {"comment": "API关键词配置表", "mysql_charset": "utf8mb4", "mysql_engine": "InnoDB"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="配置ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属用户ID")
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属闲鱼账号主键")
    # 历史表补字段时允许空值，唯一索引可兼容多条旧记录；所有新建请求仍强制提供标识。
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, comment="保存请求标识，用于防止重试重复保存，历史记录可为空")
    request_item_scope: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="首次保存的商品范围摘要，用于校验批量请求重试，历史记录可为空")
    keyword: Mapped[str] = mapped_column(Text, nullable=False, comment="触发关键字，多个关键字使用英文逗号分隔")
    item_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="绑定商品ID，空值表示通用关键词")
    url: Mapped[str] = mapped_column(String(2048), nullable=False, comment="API地址")
    method: Mapped[str] = mapped_column(String(8), nullable=False, server_default="GET", comment="请求方法")
    timeout: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60", comment="超时时间，单位秒")
    headers: Mapped[dict[str, str] | None] = mapped_column(JSON, comment="请求头JSON对象")
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON, comment="请求参数JSON对象，支持商品ID和消息内容占位符")
    response_field: Mapped[str] = mapped_column(String(255), nullable=False, server_default="", comment="响应取值字段路径")
    sync_confirm_delivery: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"), comment="是否同步确认发货")
    trigger_after_order: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"), comment="是否下单后触发")
    follow_order_quantity: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"), comment="是否跟随订单数量限制触发次数")
    skip_same_message: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"), comment="是否跳过已处理成功的相同消息")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"), comment="是否删除，0正常1已删除")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=get_beijing_now_naive, server_default=text("CURRENT_TIMESTAMP"), comment="创建时间，北京时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=get_beijing_now_naive, onupdate=get_beijing_now_naive, server_default=text("CURRENT_TIMESTAMP"), comment="更新时间，北京时间")
