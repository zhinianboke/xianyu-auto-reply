"""
商品素材库模型

功能：
1. 定义商品素材库表结构（xy_product_materials）
2. 存储可复用的商品发布模板（标题、描述、价格、图片等）
3. 支持按用户隔离
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Index, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ProductMaterial(TimestampMixin, Base):
    """商品素材库表 - 存储可复用的商品发布模板"""

    __tablename__ = "xy_product_materials"
    __table_args__ = (
        Index("idx_pm_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="所属用户ID")
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="商品标题")
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="商品描述")
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, comment="价格")
    original_price: Mapped[float | None] = mapped_column(Numeric(12, 2), comment="原价")
    category: Mapped[str | None] = mapped_column(String(100), comment="商品分类")
    images: Mapped[list | None] = mapped_column(JSON, comment="图片URL列表（最多9张）")
    delivery_method: Mapped[str] = mapped_column(String(20), default="express", comment="发货方式：express-快递, pickup-自提")
    postage: Mapped[float] = mapped_column(Numeric(8, 2), default=0, comment="邮费，0表示包邮")
    address: Mapped[str | None] = mapped_column(String(200), comment="宝贝所在地")
    brand: Mapped[str | None] = mapped_column(String(100), comment="品牌")
    condition: Mapped[str] = mapped_column(String(20), default="全新", comment="成色：全新/99新/95新等")
    remark: Mapped[str | None] = mapped_column(String(500), comment="备注（仅内部使用，不发布到闲鱼）")
