"""
Cookie续期计划模型

功能：
1. 定义Cookie续期到期时间表结构（xy_cookie_refresh_schedules）
2. 按账号记录当前Cookie续期到期时间
3. 记录最近一次续期结果，供定时任务判断和追踪
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class CookieRefreshSchedule(TimestampMixin, Base):
    """Cookie续期计划表。"""

    __tablename__ = "xy_cookie_refresh_schedules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True, comment="账号ID")
    expire_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="当前Cookie续期到期时间")
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime, comment="最近一次续期成功时间")
    last_status: Mapped[str | None] = mapped_column(String(20), comment="最近一次状态：initialized/success/failed")
    last_error_message: Mapped[str | None] = mapped_column(String(500), comment="最近一次错误信息")
