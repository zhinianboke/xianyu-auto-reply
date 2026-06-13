"""
对接记录模型

存储用户对接货源卡券的记录，包含加价金额、对接名称等信息
支持二级分销：level=1为一级分销（直接对接卡券拥有者），level=2为二级分销（对接一级分销商）
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class DockRecord(Base):
    """对接记录表"""

    __tablename__ = "xy_dock_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment='用户ID')
    card_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment='来源卡券ID')
    dock_name: Mapped[str] = mapped_column(String(255), nullable=False, comment='对接名称')
    markup_amount: Mapped[str] = mapped_column(String(32), nullable=False, default='0.00', comment='加价金额')
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment='备注')
    delivery_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment='发货次数')
    status: Mapped[bool] = mapped_column(Boolean, default=True, comment='对接状态：启用/停用')
    disable_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='禁用原因')
    # 上级锁定标记：由卡券拥有者/上级分销主禁用时置为 True，分销商自身无法将其重新启用，
    # 仅上级（owner-update / cascade-status）或管理员可解除。用于防止下级覆盖上级的禁用决定。
    owner_disabled: Mapped[bool] = mapped_column(Boolean, default=False, comment='是否被上级禁用锁定：1是 0否')
    
    # 二级分销字段
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment='分销层级：1=一级分销，2=二级分销')
    parent_dock_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment='上级对接记录ID，一级分销为NULL')
    source_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment='上级分销商用户ID，一级分销为NULL')
    allow_sub_dock: Mapped[bool] = mapped_column(Boolean, default=False, comment='是否允许下级对接')
    sub_dock_price: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment='给下级的对接价格（一级分销商设定）')
    sub_dock_visibility: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment='下级对接可见性：public-所有人可见，dealer_only-仅绑定对接码的分销商可见')
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment='创建时间'
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间'
    )
