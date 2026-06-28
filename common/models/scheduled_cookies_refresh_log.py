"""
COOKIES刷新日志模型

功能：
1. 定义COOKIES刷新日志表结构（xy_scheduled_cookies_refresh_log）
2. 记录每次定时任务执行时账号的初始化、刷新成功或失败结果
3. 支持按批次ID查询同一次定时任务的所有日志
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ScheduledCookiesRefreshLog(TimestampMixin, Base):
    """COOKIES刷新日志表。"""

    __tablename__ = "xy_scheduled_cookies_refresh_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="批次ID")
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True, comment="账号ID")
    status: Mapped[str] = mapped_column(String(20), nullable=False, comment="状态：initialized/success/failed")
    updated_cookie_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="本次增量更新的Cookie字段数量")
    next_expire_at: Mapped[datetime | None] = mapped_column(DateTime, comment="下次到期时间")
    error_message: Mapped[str | None] = mapped_column(String(500), comment="错误信息或处理说明")
