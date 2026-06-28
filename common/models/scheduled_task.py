"""
定时任务配置模型

功能：
1. 存储定时任务配置（间隔时间、是否启用）
2. 支持定时补发货和定时补评价两种任务
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ScheduledTask(TimestampMixin, Base):
    """定时任务配置表"""

    __tablename__ = "xy_scheduled_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    task_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="任务代码")
    task_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="任务名称")
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60, comment="执行间隔(秒)")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    description: Mapped[str | None] = mapped_column(Text, comment="任务描述")

