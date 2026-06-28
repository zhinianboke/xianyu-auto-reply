"""
用户模型

功能：
1. 定义用户表结构（xy_users）
2. 用户状态枚举（ACTIVE/INACTIVE/SUSPENDED/DELETED）
3. 用户角色枚举（ADMIN/OPERATOR/MEMBER）
4. 关联关系：账号、卡券
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base_class import Base, TimestampMixin


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    MEMBER = "MEMBER"


class User(TimestampMixin, Base):
    """用户表"""
    __tablename__ = "xy_users"
    __table_args__ = (
        Index("idx_user_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="用户ID")
    external_id: Mapped[str | None] = mapped_column(String(64), index=True, comment="外部ID")
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="用户名")
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, comment="邮箱")
    phone: Mapped[str | None] = mapped_column(String(32), comment="手机号")
    password_hash: Mapped[str] = mapped_column(String(255), comment="密码哈希")
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus),
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
        comment="用户状态",
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole),
        default=UserRole.MEMBER,
        server_default=UserRole.MEMBER.value,
        comment="用户角色",
    )
    account_limit: Mapped[int | None] = mapped_column(nullable=True, comment="可添加账号数量")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="最后登录时间")
    login_fail_count: Mapped[int] = mapped_column(default=0, server_default="0", comment="登录失败次数")
    login_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="登录锁定截止时间")
    dock_code: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True, comment='对接码，用于分销商识别')
    # 分销秘钥：32位随机字符，全局唯一，支持更换；用于分销接口的身份校验
    secret_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, comment='分销秘钥，32位随机字符，全局唯一')
    # 账号到期日（精确到时分秒）：NULL 表示永不过期；到期后 WebSocket 不再连接并自动禁用账号
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment='账号到期日（精确到秒，NULL=永不过期）')

    # 关系定义 - 无外键约束，通过代码控制数据一致性
    accounts: Mapped[list["XYAccount"]] = relationship(
        "XYAccount",
        primaryjoin="User.id == XYAccount.owner_id",
        foreign_keys="XYAccount.owner_id",
        back_populates="owner",
        viewonly=True,
    )
    cards: Mapped[list["Card"]] = relationship(
        "Card",
        primaryjoin="User.id == Card.user_id",
        foreign_keys="Card.user_id",
        back_populates="user",
        viewonly=True,
    )

