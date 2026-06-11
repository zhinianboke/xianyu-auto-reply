"""
风控日志模型

功能：
1. 定义风控日志表结构（xy_risk_control_logs）
2. 记录滑块验证等风控事件
3. 跟踪处理状态和结果
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class XYRiskControlLog(Base):
    """风控日志表 - 记录账号的风控事件"""

    __tablename__ = "xy_risk_control_logs"
    __table_args__ = (
        Index("idx_rcl_identifier_status_created", "account_identifier", "processing_status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    account_pk: Mapped[int | None] = mapped_column(
        "account_id",
        BigInteger,
        nullable=True,
        index=True,
    )
    account_identifier: Mapped[str | None] = mapped_column(String(80))
    event_type: Mapped[str] = mapped_column(String(64), default="slider_captcha")
    event_description: Mapped[str | None] = mapped_column(Text)
    processing_result: Mapped[str | None] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(String(32), default="processing")
    # 验证通过的引擎：playwright-主引擎 / drissionpage-兜底引擎；未涉及验证或失败时为 NULL
    captcha_engine: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

