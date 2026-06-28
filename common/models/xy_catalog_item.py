"""
商品目录模型

功能：
1. 定义商品目录表结构（xy_catalog_items）
2. 缓存闲鱼商品信息（标题、价格等）
3. 关联账号，支持商品元数据存储
4. 支持商品级别AI提示词配置
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db.base_class import Base


class XYCatalogItem(Base):
    """商品目录表 - 缓存闲鱼商品信息"""

    __tablename__ = "xy_catalog_items"
    __table_args__ = (
        # 复合索引：加速与 xy_keyword_rules 的 (account_pk, item_id) JOIN 查询
        Index("idx_cat_account_item", "account_id", "item_id"),
        # 复合索引：加速商品管理列表分页查询（owner_id 过滤 + created_at 倒序）
        Index("idx_cat_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="商品ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="所属用户ID")
    account_pk: Mapped[int] = mapped_column(
        "account_id",
        BigInteger,
        index=True,
        comment="关联账号ID",
    )
    item_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="商品标识")
    title: Mapped[str | None] = mapped_column(String(255), comment="商品标题")
    price: Mapped[str | None] = mapped_column(String(32), comment="商品价格")
    ai_prompt: Mapped[str | None] = mapped_column(Text, comment="商品AI提示词")
    is_polished: Mapped[bool | None] = mapped_column("is_polished", default=False, comment="是否擦亮")
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, comment="商品元数据")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="创建时间")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=datetime.now, comment="更新时间")

    account: Mapped["XYAccount"] = relationship(
        "XYAccount",
        primaryjoin="XYCatalogItem.account_pk == XYAccount.id",
        foreign_keys="[XYCatalogItem.account_pk]",
        back_populates="catalog_items",
        viewonly=True,
    )

    # 多对多关联关系 - 通过 xy_card_item_relations 表关联卡券
    card_relations = relationship(
        "CardItemRelation",
        primaryjoin="XYCatalogItem.item_id == CardItemRelation.item_id",
        foreign_keys="[CardItemRelation.item_id]",
        viewonly=True,
        lazy="select",
    )

