"""
共享扫码登录兼职工作者模型

功能：
1. 定义共享扫码登录兼职工作者表结构（xy_shared_scan_workers）
2. 每个兼职加入共享会话后创建一条记录
3. 记录兼职独立的二维码、扫码状态、登录后的账号信息
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class SharedScanWorker(TimestampMixin, Base):
    """共享扫码登录兼职工作者表"""

    __tablename__ = "xy_shared_scan_workers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    shared_session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="关联的共享会话ID")
    sub_session_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True, comment="兼职子会话唯一ID（UUID）")
    xianyu_session_id: Mapped[str | None] = mapped_column(String(36), comment="关联的闲鱼QR登录会话ID（qr_login_manager中的session）")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="qrcode_ready", comment="状态：qrcode_ready/scanning/success/failed")
    qr_code_url: Mapped[str | None] = mapped_column(Text, comment="二维码图片base64 data URL")
    account_id: Mapped[str | None] = mapped_column(String(80), index=True, comment="扫码成功后的闲鱼账号ID（unb）")
    cookie_saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="Cookie是否已保存到账号表")
