"""
Token 续期执行日志模型。

功能：
1. 定义 Token 续期执行日志表结构。
2. 记录每次 token_renewal 定时任务的逐账号执行结果。
3. 支持按批次 ID 查询同一次任务的所有明细。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ScheduledTokenRenewalLog(TimestampMixin, Base):
    """Token 续期执行日志表。"""

    __tablename__ = "xy_scheduled_token_renewal_log"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键ID",
    )
    batch_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        comment="批次ID，标识一次定时任务执行",
    )
    account_id: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
        comment="账号ID",
    )
    token_user_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Token缓存用户ID（myid）",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="状态：success/failed",
    )
    renew_expire_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="续期Token到期时间",
    )
    error_message: Mapped[str | None] = mapped_column(
        String(500),
        comment="执行结果说明或错误信息",
    )
