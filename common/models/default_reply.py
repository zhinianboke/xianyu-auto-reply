"""默认回复模型"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class DefaultReply(Base):
    """默认回复设置表（支持账号级别和商品级别）"""

    __tablename__ = "xy_default_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)  # 对应 xy_accounts.account_id
    item_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)  # 商品ID，空为账号默认回复
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # 回复类型：text-文本回复（可附带图片），api-调用外部API获取回复内容
    reply_type: Mapped[str] = mapped_column(String(16), default="text", server_default="text")
    reply_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reply_image: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # 回复图片URL
    # API 类型默认回复配置
    api_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)  # API 地址（POST）
    api_timeout: Mapped[int] = mapped_column(Integer, default=80, server_default="80")  # API 请求超时时间（秒）
    reply_once: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否只回复一次
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class DefaultReplyRecord(Base):
    """默认回复记录表（记录已回复过的用户，支持账号级别和商品级别）"""

    __tablename__ = "xy_default_reply_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)  # 对应 xy_accounts.account_id
    item_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)  # 商品ID，空为账号默认回复
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # 被回复的用户ID
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

