"""
广告模型

功能：
1. 定义广告表结构（xy_advertisements）
2. 支持广告申请和管理
3. 广告类型：轮播图、文字广告
4. 审核状态：待复核、已复核
"""
from __future__ import annotations

from datetime import date
from enum import Enum

from sqlalchemy import BigInteger, Integer, String, Text, Date, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class AdType(str, Enum):
    """广告类型"""
    CAROUSEL = "carousel"  # 轮播图
    TEXT = "text"  # 文字广告


class AdStatus(str, Enum):
    """审核状态"""
    UNPAID = "unpaid"  # 待付款
    PENDING = "pending"  # 待复核
    APPROVED = "approved"  # 已复核


class Advertisement(TimestampMixin, Base):
    """广告表"""
    __tablename__ = "xy_advertisements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="广告ID")
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="申请用户ID")
    title: Mapped[str] = mapped_column(String(200), comment="广告标题")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="广告正文")
    link: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="广告链接")
    expire_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="到期日期")
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="图片URL")
    ad_type: Mapped[AdType] = mapped_column(
        SQLEnum(AdType, values_callable=lambda x: [e.value for e in x]),
        default=AdType.TEXT,
        comment="广告类型"
    )
    months: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="购买月数")
    total_amount: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="广告总费用")
    status: Mapped[AdStatus] = mapped_column(
        SQLEnum(AdStatus, values_callable=lambda x: [e.value for e in x]),
        default=AdStatus.UNPAID,
        comment="审核状态"
    )
