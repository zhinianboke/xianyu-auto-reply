"""
定时补评价执行日志模型

功能：
1. 定义定时补评价执行日志表结构（scheduled_rate_log）
2. 记录每次定时任务执行的评价结果
3. 支持按批次ID查询同一次定时任务的所有日志
"""
from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ScheduledRateLog(TimestampMixin, Base):
    """定时补评价执行日志表"""

    __tablename__ = "xy_scheduled_rate_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="批次ID，标识一次定时任务执行")
    account_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True, comment="账号ID")
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="订单号")
    status: Mapped[str] = mapped_column(String(20), nullable=False, comment="状态：success/failed")
    error_message: Mapped[str | None] = mapped_column(String(500), comment="错误信息")

