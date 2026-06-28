"""卡券模型"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base_class import Base


class Card(Base):
    """卡券表"""

    __tablename__ = "xy_cards"

    # 复合索引：加速按 user_id 分页查询（ORDER BY id DESC）
    # 复合索引：加速按 user_id + enabled 过滤（发货匹配场景）
    __table_args__ = (
        Index("idx_cards_user_id_desc", "user_id", "id"),
        Index("idx_cards_user_enabled", "user_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment='卡券ID')
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment='所属用户ID')
    item_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True, comment='关联商品ID')  # 关联商品ID
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment='卡券名称')
    type: Mapped[str] = mapped_column(String(50), nullable=False, comment='卡券类型(api/text/data/image)')  # api, text, data, image
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment='卡券描述')
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment='是否启用')
    delay_seconds: Mapped[int] = mapped_column(Integer, default=0, comment='延迟秒数')
    delivery_count: Mapped[int] = mapped_column(Integer, default=0, comment='发货次数')
    price: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment='对接价格')
    is_dockable: Mapped[bool] = mapped_column(Boolean, default=False, comment='是否可对接')
    fee_payer: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment='手续费支付方式：distributor-分销主支付，dealer-分销商支付')
    min_price: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment='最低售价')
    dock_visibility: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment='对接可见性：public-所有人可见，dealer_only-仅分销商可见')
    
    # 多规格支持
    is_multi_spec: Mapped[bool] = mapped_column(Boolean, default=False, comment='是否多规格')
    spec_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='规格名称')
    spec_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='规格值')

    # 根据类型存储不同内容
    api_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment='API配置(JSON)')  # JSON 格式
    text_content: Mapped[Optional[str]] = mapped_column(LONGTEXT, nullable=True, comment='文本卡券内容')  # 文本卡券内容，使用 LONGTEXT 存储超大内容
    data_content: Mapped[Optional[str]] = mapped_column(LONGTEXT, nullable=True, comment='批量数据（卡密）内容')  # 批量数据（卡密）内容，使用 LONGTEXT 存储超大内容
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment='图片URL')
    image_urls: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment='多图片URL列表(JSON数组，最多3张)')  # JSON数组，最多3张图片

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')

    # 关系 - 无外键约束
    user = relationship(
        "User",
        primaryjoin="Card.user_id == User.id",
        foreign_keys="[Card.user_id]",
        back_populates="cards",
        viewonly=True,
    )

    # 多对多关联关系 - 通过 xy_card_item_relations 表关联商品
    item_relations = relationship(
        "CardItemRelation",
        primaryjoin="Card.id == CardItemRelation.card_id",
        foreign_keys="[CardItemRelation.card_id]",
        viewonly=True,
        lazy="select",
    )

