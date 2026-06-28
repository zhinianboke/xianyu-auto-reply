"""
返佣系统 - 推广账号模型

功能：
1. 定义推广账号表结构（fy_accounts）
2. 账号类型枚举（淘宝/京东/美团）
3. 存储账号Cookie、状态、备注等信息
4. 关联用户表（xy_users）
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base_class import Base, TimestampMixin


class FYAccountType(str, enum.Enum):
    """账号类型枚举"""
    TAOBAO = "TAOBAO"      # 淘宝
    JD = "JD"              # 京东
    MEITUAN = "MEITUAN"    # 美团


class FYAccount(TimestampMixin, Base):
    """返佣系统推广账号表"""

    __tablename__ = "fy_accounts"
    __table_args__ = (
        Index("idx_fy_account_owner", "owner_id"),
        Index("idx_fy_account_type", "account_type"),
        Index("idx_fy_account_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, comment="所属用户ID")
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True, comment="账号标识")
    account_type: Mapped[FYAccountType] = mapped_column(
        Enum(FYAccountType),
        default=FYAccountType.TAOBAO,
        server_default=FYAccountType.TAOBAO.value,
        comment="账号类型：TAOBAO/JD/MEITUAN",
    )
    display_name: Mapped[str | None] = mapped_column(String(120), comment="显示名称")
    cookie: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="账号Cookie")
    app_key: Mapped[str | None] = mapped_column(String(80), comment="淘宝开放平台AppKey")
    app_secret: Mapped[str | None] = mapped_column(String(200), comment="淘宝开放平台AppSecret")
    adzone_id: Mapped[str | None] = mapped_column(String(80), comment="淘宝推广位ID")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", comment="是否启用")
    remark: Mapped[str | None] = mapped_column(String(255), comment="备注")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最后登录时间")
    disable_reason: Mapped[str | None] = mapped_column(String(255), comment="禁用原因")

    # 关系定义 - 无外键约束，通过代码控制数据一致性
    owner: Mapped["User"] = relationship(
        "User",
        primaryjoin="FYAccount.owner_id == User.id",
        foreign_keys="[FYAccount.owner_id]",
        viewonly=True,
    )
