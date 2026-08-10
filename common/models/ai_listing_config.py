"""
AI铺货配置模型

保存用户的AI铺货参数，用于批量生成商品素材。
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Index, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class AiListingConfig(TimestampMixin, Base):
    """AI铺货配置表"""

    __tablename__ = "xy_ai_listing_configs"
    __table_args__ = (
        Index("idx_ai_listing_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="所属用户ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="配置名称")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, comment="商品生成提示词")
    reference_text: Mapped[str | None] = mapped_column(Text, comment="参考文案")
    price_mode: Mapped[str] = mapped_column(String(20), default="fixed", comment="价格模式：fixed/range")
    fixed_price: Mapped[float | None] = mapped_column(Numeric(12, 2), comment="固定价格")
    price_min: Mapped[float | None] = mapped_column(Numeric(12, 2), comment="最低价格")
    price_max: Mapped[float | None] = mapped_column(Numeric(12, 2), comment="最高价格")
    text_api_url: Mapped[str] = mapped_column(String(500), nullable=False, comment="文案AI接口地址")
    text_api_key: Mapped[str] = mapped_column(Text, nullable=False, comment="文案AI Key")
    text_model: Mapped[str] = mapped_column(String(120), nullable=False, comment="文案AI模型")
    image_mode: Mapped[str] = mapped_column(String(20), default="random", comment="图片模式：ai/random")
    image_api_url: Mapped[str | None] = mapped_column(String(500), comment="图片AI接口地址")
    image_api_key: Mapped[str | None] = mapped_column(Text, comment="图片AI Key")
    image_model: Mapped[str | None] = mapped_column(String(120), comment="图片AI模型")
    image_prompt: Mapped[str | None] = mapped_column(Text, comment="图片生成提示词")
    image_polish_enabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否启用图片提示词AI润色")
    image_polish_sequential: Mapped[bool] = mapped_column(Boolean, default=False, comment="多图是否保持关联")
    random_images: Mapped[list | None] = mapped_column(JSON, comment="随机图库")
    random_image_count: Mapped[int] = mapped_column(Integer, default=1, comment="随机选图数量")
    material_defaults: Mapped[dict | None] = mapped_column(JSON, comment="素材默认字段")
