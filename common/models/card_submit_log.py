"""
卡密提交日志模型。

功能：
1. 记录订单卡密提交接口的完整返回值
2. 记录每次提交尝试的成功状态和处理结果
3. 为提交后通知买家任务提供结果数据
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class XYCardSubmitLog(Base):
    """卡密提交日志表，只追加提交记录。"""

    __tablename__ = "xy_card_submit_logs"
    __table_args__ = (
        Index("idx_card_submit_owner_created", "owner_id", "created_at"),
        Index("idx_card_submit_order_created", "order_no", "created_at"),
        Index("idx_card_submit_success_created", "success", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="所属用户ID")
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="订单号")
    response_body: Mapped[str] = mapped_column(LONGTEXT, nullable=False, comment="提交接口完整返回值")
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否提交成功")
    result_message: Mapped[str] = mapped_column(Text, nullable=False, comment="提交结果说明")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, comment="创建时间"
    )
