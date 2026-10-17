"""
数据字典模型

功能：
1. 定义通用数据字典表结构（xy_data_dictionaries）
2. 为枚举值提供统一的中文名称、排序与启用状态
3. 邮件日志的触发操作、发送结果等枚举统一从本表读取

说明：字段类型、长度与注释均与 common/db/init_database.py 中 xy_data_dictionaries 建表 DDL 保持一致。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class XYDataDictionary(Base):
    """通用数据字典表。"""

    __tablename__ = "xy_data_dictionaries"
    __table_args__ = (
        UniqueConstraint("dict_type", "dict_value", name="uk_dd_type_value"),
        Index("idx_dd_type_sort", "dict_type", "sort_order"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="字典项ID")
    dict_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="字典类型")
    dict_value: Mapped[str] = mapped_column(String(64), nullable=False, comment="字典值")
    dict_label: Mapped[str] = mapped_column(String(128), nullable=False, comment="中文名称")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序序号")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用：1-启用，0-禁用")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )


__all__ = ["XYDataDictionary"]