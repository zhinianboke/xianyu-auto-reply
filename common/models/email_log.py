"""
邮件发送日志模型

功能：
1. 定义邮件发送日志表结构（xy_email_logs）
2. 记录每一次触发邮件发送的尝试与结果（成功、失败、限流或配置缺失均写入）
3. 支持按邮箱、触发操作、发送结果、时间范围筛选

设计要点：
- 仅追加写入，不提供 UPDATE / DELETE 业务接口
- owner_id 为触发用户 ID；找不到对应用户时为空
- trigger_operation 的取值统一落入数据字典
- 字段类型、长度与注释均与 common/db/init_database.py 中 xy_email_logs 建表 DDL 保持一致
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class XYEmailLog(Base):
    """邮件发送日志表。"""

    __tablename__ = "xy_email_logs"
    __table_args__ = (
        Index("idx_el_owner_id", "owner_id"),
        Index("idx_el_trigger_operation", "trigger_operation"),
        Index("idx_el_created_at", "created_at"),
        Index("idx_el_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    owner_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="触发用户ID（找不到对应用户时为空）"
    )
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False, comment="收件邮箱")
    trigger_operation: Mapped[str] = mapped_column(String(64), nullable=False, comment="触发操作")
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否成功：1-成功，0-失败")
    client_ip: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="客户端IP")
    result_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="结果说明（成功结果或失败原因）")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="发生时间"
    )


__all__ = ["XYEmailLog"]