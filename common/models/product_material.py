"""
商品素材库模型

功能：
1. 定义商品素材库表结构（xy_product_materials）
2. 存储可复用的商品发布模板（标题、描述、价格、图片等）
3. 支持按用户隔离
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Index, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class ProductMaterial(TimestampMixin, Base):
    """商品素材库表 - 存储可复用的商品发布模板"""

    __tablename__ = "xy_product_materials"
    __table_args__ = (
        Index("idx_pm_user_created", "user_id", "created_at"),
        Index("idx_pm_platform_category", "platform_category_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="所属用户ID")
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="商品标题")
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="商品描述")
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, comment="价格")
    original_price: Mapped[float | None] = mapped_column(Numeric(12, 2), comment="原价")
    category: Mapped[str | None] = mapped_column(String(100), comment="商品分类")
    platform_category_id: Mapped[str | None] = mapped_column(String(64), comment="平台末级分类ID（catId）")
    platform_category_name: Mapped[str | None] = mapped_column(String(100), comment="平台末级分类名称（catName）")
    platform_channel_category_id: Mapped[str | None] = mapped_column(String(64), comment="平台频道分类ID（channelCatId）")
    platform_channel_category_name: Mapped[str | None] = mapped_column(String(100), comment="平台频道分类名称（channelCatName）")
    platform_leaf_id: Mapped[str | None] = mapped_column(String(64), comment="平台叶子分类ID（leafId）")
    platform_tb_category_id: Mapped[str | None] = mapped_column(String(64), comment="淘宝分类ID（tbCatId）")
    platform_category_path: Mapped[list | None] = mapped_column(JSON, comment="平台多级分类路径（各级ID和名称）")
    platform_attributes: Mapped[list | None] = mapped_column(JSON, comment="平台属性标签列表（itemLabelExtList）")
    category_source: Mapped[str] = mapped_column(String(20), default="manual", comment="分类来源：manual-手动，recommendation-推荐")
    category_confidence: Mapped[float | None] = mapped_column(Numeric(8, 6), comment="分类推荐置信度")
    images: Mapped[list | None] = mapped_column(JSON, comment="图片URL列表（最多9张）")
    videos: Mapped[list | None] = mapped_column(JSON, comment="视频素材列表（URL、文件ID、尺寸等）")
    specifications: Mapped[list | None] = mapped_column(JSON, comment="商品规格列表")
    sku_rows: Mapped[list | None] = mapped_column(JSON, comment="规格组合价格和库存列表")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="发布数量")
    delivery_method: Mapped[str] = mapped_column(String(20), default="express", comment="发货方式：express-快递, pickup-自提")
    shipping_method: Mapped[str] = mapped_column(String(20), default="free", comment="运费方式：free/distance/fixed/template/none")
    support_pickup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否支持自提")
    postage: Mapped[float] = mapped_column(Numeric(8, 2), default=0, comment="邮费，0表示包邮")
    address: Mapped[str | None] = mapped_column(String(200), comment="宝贝所在地")
    address_expected_text: Mapped[str | None] = mapped_column(String(200), comment="所在地选择时的期望文本")
    brand: Mapped[str | None] = mapped_column(String(100), comment="品牌")
    condition: Mapped[str] = mapped_column(String(20), default="全新", comment="成色：全新/99新/95新等")
    remark: Mapped[str | None] = mapped_column(String(500), comment="备注（仅内部使用，不发布到闲鱼）")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否已删除（软删除）")
