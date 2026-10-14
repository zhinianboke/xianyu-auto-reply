"""
用户登录日志模型

功能：
1. 定义系统用户登录日志表结构（xy_user_login_logs）
2. 记录系统用户登录本系统的每一次尝试与结果（成功 / 失败都会写入）
3. 支持按用户、登录方式、时间范围、关键字筛选

设计要点：
- 登录成功与失败均写入一条记录，登录失败时 owner_id 为空
- login_method 取值：username_password（账号密码）/ email_password（邮箱密码）/ email_code（邮箱验证码）
- 该表只追加，不做 UPDATE / DELETE
- 与「账号登录日志（xy_account_login_logs，记录闲鱼账号密码登录）」相互独立，互不影响
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class XYUserLoginLog(Base):
    """用户登录日志表 - 记录系统用户登录本系统的每一次尝试与结果"""

    __tablename__ = "xy_user_login_logs"
    __table_args__ = (
        Index("idx_ull_owner_created", "owner_id", "created_at"),
        Index("idx_ull_created_at", "created_at"),
        Index("idx_ull_login_method", "login_method"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    # 登录成功时记录登录用户ID（所属用户），登录失败时为 NULL
    owner_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="登录用户ID（登录失败时为空）"
    )
    # 登录账号快照（用户名或邮箱），失败时用于排查是哪个账号尝试登录
    login_account: Mapped[str | None] = mapped_column(String(255), comment="登录账号（用户名或邮箱）")
    # 登录方式：username_password/email_password/email_code
    login_method: Mapped[str] = mapped_column(
        String(32), comment="登录方式：username_password/email_password/email_code"
    )
    # 是否登录成功
    success: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否登录成功")
    # 客户端 IP（优先取 X-Forwarded-For）
    client_ip: Mapped[str | None] = mapped_column(String(64), comment="客户端IP")
    # 结果说明：成功提示或失败原因
    result_message: Mapped[str | None] = mapped_column(String(512), comment="结果说明")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="创建时间",
    )