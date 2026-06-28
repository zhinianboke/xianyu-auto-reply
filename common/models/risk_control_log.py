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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="所属用户ID")
    account_pk: Mapped[int | None] = mapped_column(
        "account_id",
        BigInteger,
        nullable=True,
        index=True,
        comment="关联账号ID",
    )
    account_identifier: Mapped[str | None] = mapped_column(String(80), comment="账号标识")
    event_type: Mapped[str] = mapped_column(String(64), default="slider_captcha", comment="事件类型")
    event_description: Mapped[str | None] = mapped_column(Text, comment="事件描述")
    processing_result: Mapped[str | None] = mapped_column(Text, comment="处理结果")
    processing_status: Mapped[str] = mapped_column(String(32), default="processing", comment="处理状态")
    # 验证通过的引擎：playwright-主引擎 / drissionpage-兜底引擎 / real_mouse-真人鼠标引擎；未涉及验证或失败时为 NULL
    captcha_engine: Mapped[str | None] = mapped_column(String(32), comment="验证通过引擎：playwright-主引擎/drissionpage-兜底引擎/real_mouse-真人鼠标引擎")
    # 调用类型：local-本机（系统内部触发）/ remote-远程（外部凭秘钥调用过滑块接口）
    call_type: Mapped[str] = mapped_column(String(16), default="local", comment="调用类型：local-本机/remote-远程(外部凭秘钥调用)")
    # 调用用户：仅远程调用时记录，按传入秘钥查到的用户名；本机调用为 NULL
    call_user: Mapped[str | None] = mapped_column(String(128), comment="调用用户：仅远程调用记录(按秘钥查到的用户名)")
    error_message: Mapped[str | None] = mapped_column(Text, comment="错误信息")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

