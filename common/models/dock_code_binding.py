"""
对接码绑定模型

存储用户绑定的对接码记录，用于货源广场中 dealer_only 卡券的可见性控制
用户通过输入对接码绑定供应商，绑定后可在货源广场看到该供应商的 dealer_only 卡券
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class DockCodeBinding(Base):
    """对接码绑定表"""

    __tablename__ = "xy_dock_code_bindings"
    __table_args__ = (
        UniqueConstraint('user_id', 'target_user_id', name='uq_user_target'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment='绑定用户ID（分销商）')
    dock_code: Mapped[str] = mapped_column(String(32), nullable=False, comment='对接码')
    target_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment='对接码拥有者用户ID（供应商）')
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment='绑定时间'
    )
