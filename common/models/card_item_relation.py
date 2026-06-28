"""
卡券与商品多对多关联模型

功能：
1. 定义卡券与商品的多对多关联表（xy_card_item_relations）
2. 支持一个卡券关联多个商品，一个商品关联多个卡券
3. 冗余 user_id 字段，简化按用户过滤查询
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base


class CardItemRelation(Base):
    """卡券商品关联表 - 多对多关系"""

    __tablename__ = "xy_card_item_relations"

    # 复合索引：加速 item_id + card_id 的 JOIN 查询（关联卡券弹窗、发货匹配）
    # 复合索引：加速按 user_id + item_id 过滤（用户维度的商品卡券查询）
    __table_args__ = (
        Index("idx_cir_item_card", "item_id", "card_id"),
        Index("idx_cir_user_item", "user_id", "item_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="所属用户ID")
    card_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="卡券ID")
    item_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="商品ID")
    source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="own", comment="卡券来源：own-自有，dock_l1-一级对接，dock_l2-二级对接")
    dock_record_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0", comment="对接记录ID（对接卡券时关联，0表示自有卡券）")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
