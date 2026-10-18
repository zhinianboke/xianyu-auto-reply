"""卡密处理结果查询日志模型。"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column
from common.db.base_class import Base


class XYCardProcessResultLog(Base):
    """记录卡密状态查询请求、响应和触发场景。"""

    __tablename__ = "xy_card_process_result_logs"
    __table_args__ = (
        Index("idx_card_process_owner_created", "owner_id", "created_at"),
        Index("idx_card_process_order_created", "order_no", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="日志ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属用户ID")
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="订单号")
    request_body: Mapped[str] = mapped_column(LONGTEXT, nullable=False, comment="查询接口请求参数")
    response_body: Mapped[str] = mapped_column(LONGTEXT, nullable=False, comment="查询接口返回值")
    trigger_scene: Mapped[str] = mapped_column(String(32), nullable=False, comment="触发场景")
    success: Mapped[bool] = mapped_column(default=False, nullable=False, comment="是否处理成功")
    result_message: Mapped[str] = mapped_column(Text, nullable=False, comment="处理结果说明")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="创建时间")
