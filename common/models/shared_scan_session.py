"""
共享扫码登录会话模型

功能：
1. 定义共享扫码登录会话表结构（xy_shared_scan_sessions）
2. 管理员创建共享会话，生成可分享给多个兼职的链接
3. 一个会话可以被多个兼职同时加入，各自独立扫码登录
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class SharedScanSession(TimestampMixin, Base):
    """共享扫码登录会话表"""

    __tablename__ = "xy_shared_scan_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True, comment="会话唯一ID（UUID）")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="创建者用户ID")
    owner_username: Mapped[str] = mapped_column(String(120), nullable=False, comment="创建者用户名")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", comment="会话状态：active/closed")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="过期时间（默认72小时）")
