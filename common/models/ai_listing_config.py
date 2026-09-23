"""
AI 铺货配置模型

功能：
1. 定义 AI 铺货配置表结构（xy_ai_listing_configs）
2. 按用户隔离，一个用户可保存多套配置（不同模型 / 不同风格）
3. 文案生成为必备能力，图片生成为可选开关（默认关闭）
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class AiListingConfig(TimestampMixin, Base):
    """AI 铺货配置表 - 记录调用 AI 生成素材所需的模型与参数"""

    __tablename__ = "xy_ai_listing_configs"
    __table_args__ = (
        Index("idx_alc_owner_deleted", "owner_id", "is_deleted"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="归属用户（本系统用户ID）")
    name: Mapped[str] = mapped_column(String(80), nullable=False, comment="配置名称")
    provider_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="openai_compatible", comment="服务商类型：openai_compatible 等"
    )

    # 文案生成（必填）
    text_base_url: Mapped[str] = mapped_column(String(300), nullable=False, comment="文案接口地址")
    text_api_key: Mapped[str] = mapped_column(String(500), nullable=False, comment="文案接口密钥")
    text_model: Mapped[str] = mapped_column(String(100), nullable=False, comment="文案模型名称")
    text_temperature: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, default=Decimal("0.70"), comment="文案生成温度"
    )
    text_max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2048, comment="文案生成最大token数")
    prompt_template: Mapped[str | None] = mapped_column(Text, comment="自定义提示词模板（为空则用内置模板）")

    # 图片生成（可选，默认关闭）
    image_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否启用AI图片生成"
    )
    image_base_url: Mapped[str | None] = mapped_column(String(300), comment="图片接口地址")
    image_api_key: Mapped[str | None] = mapped_column(String(500), comment="图片接口密钥")
    image_model: Mapped[str | None] = mapped_column(String(100), comment="图片模型名称")
    image_size: Mapped[str] = mapped_column(
        String(20), nullable=False, default="1024x1024", comment="图片尺寸，如 1024x1024"
    )
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="每条素材生成图片数量（1~9）")

    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否已删除（软删除）"
    )
