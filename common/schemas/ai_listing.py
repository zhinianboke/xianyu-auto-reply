"""
AI 铺货请求/响应 Schema

功能：
1. 定义 AI 铺货配置的创建与更新请求模型
2. 定义 AI 铺货任务的启动请求模型（含价格模式与素材默认值白名单）
3. 校验规则与素材库创建接口保持一致，避免生成的数据入库后无法在前端编辑保存
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

# 素材默认值中图片数量上限，与素材库 images 字段一致
MATERIAL_IMAGE_MAX_COUNT = 9


class AiListingConfigRequest(BaseModel):
    """AI 铺货配置的创建/更新请求

    更新时 ``text_api_key`` / ``image_api_key`` 传空字符串表示"不修改原密钥"，
    前端展示的是脱敏值，不会把明文回传。
    """

    name: str = Field(..., min_length=1, max_length=80, description="配置名称")
    provider_type: str = Field("openai_compatible", max_length=30, description="服务商类型")

    text_base_url: str = Field(..., min_length=1, max_length=300, description="文案接口地址")
    text_api_key: str = Field("", max_length=500, description="文案接口密钥，更新时留空表示不修改")
    text_model: str = Field(..., min_length=1, max_length=100, description="文案模型名称")
    text_temperature: float = Field(0.7, ge=0, le=2, description="文案生成温度")
    text_max_tokens: int = Field(2048, ge=256, le=32768, description="文案生成最大token数")
    prompt_template: Optional[str] = Field(None, max_length=4000, description="自定义提示词模板")

    image_enabled: bool = Field(False, description="是否启用AI图片生成")
    image_base_url: Optional[str] = Field(None, max_length=300, description="图片接口地址")
    image_api_key: str = Field("", max_length=500, description="图片接口密钥，更新时留空表示不修改")
    image_model: Optional[str] = Field(None, max_length=100, description="图片模型名称")
    image_size: str = Field("1024x1024", pattern=r"^\d{3,4}x\d{3,4}$", description="图片尺寸，如 1024x1024")
    image_count: int = Field(
        1, ge=1, le=MATERIAL_IMAGE_MAX_COUNT, description="每条素材生成图片数量"
    )

    @model_validator(mode="after")
    def check_image_fields(self) -> "AiListingConfigRequest":
        """启用图片生成时，图片接口地址与模型必填"""
        if self.image_enabled:
            if not (self.image_base_url or "").strip():
                raise ValueError("启用AI图片生成时必须填写图片接口地址")
            if not (self.image_model or "").strip():
                raise ValueError("启用AI图片生成时必须填写图片模型名称")
        return self


class AiListingModelListRequest(BaseModel):
    """拉取可用模型列表的请求（用于配置表单里的模型下拉）"""

    provider_type: str = Field("openai_compatible", max_length=30, description="服务商类型")
    base_url: str = Field(..., min_length=1, max_length=300, description="接口地址")
    api_key: str = Field("", max_length=500, description="接口密钥；留空则使用已保存配置的密钥")
    config_id: Optional[int] = Field(None, ge=1, description="已保存的配置ID，用于复用其密钥")


class AiListingMaterialDefaults(BaseModel):
    """生成素材时套用的默认字段（白名单，不接受任意键）"""

    category: Optional[str] = Field(None, max_length=100, description="本地分类")
    condition: str = Field("全新", max_length=20, description="成色")
    brand: Optional[str] = Field(None, max_length=100, description="品牌")
    quantity: int = Field(1, ge=1, le=999999, description="发布数量")
    delivery_method: str = Field("express", pattern="^(express|pickup)$", description="发货方式")
    shipping_method: str = Field(
        "free", pattern="^(free|distance|fixed|template|none)$", description="运费方式"
    )
    support_pickup: bool = Field(False, description="是否支持自提")
    postage: float = Field(0, ge=0, le=1000, description="邮费，0到1000元")

    @model_validator(mode="after")
    def normalize_delivery_method(self) -> "AiListingMaterialDefaults":
        """以实际运费方式统一兼容字段 delivery_method。"""
        self.delivery_method = "pickup" if self.shipping_method == "none" else "express"
        return self
    address: Optional[str] = Field(None, max_length=200, description="宝贝所在地")
    remark: Optional[str] = Field(None, max_length=500, description="内部备注")
    images: List[str] = Field(
        default_factory=list,
        max_length=MATERIAL_IMAGE_MAX_COUNT,
        description="兜底图片（未启用AI图片生成时必填至少1张）",
    )


class AiListingTaskCreateRequest(BaseModel):
    """启动 AI 铺货任务的请求"""

    config_id: int = Field(..., ge=1, description="使用的AI铺货配置ID")
    keyword: str = Field(..., min_length=1, max_length=200, description="生成主题/关键词")
    count: int = Field(..., ge=1, le=50, description="生成条数")
    price_mode: str = Field("fixed", pattern="^(fixed|range)$", description="价格模式：fixed固定/range区间")
    price: Optional[float] = Field(None, gt=0, le=999999, description="固定价格")
    price_min: Optional[float] = Field(None, gt=0, le=999999, description="价格区间下限")
    price_max: Optional[float] = Field(None, gt=0, le=999999, description="价格区间上限")
    image_enabled: Optional[bool] = Field(None, description="覆盖配置里的图片生成开关；为空则沿用配置")
    material_defaults: AiListingMaterialDefaults = Field(
        default_factory=AiListingMaterialDefaults, description="素材默认字段"
    )

    @model_validator(mode="after")
    def check_price(self) -> "AiListingTaskCreateRequest":
        """按价格模式校验价格字段完整性"""
        if self.price_mode == "fixed":
            if self.price is None:
                raise ValueError("固定价格模式下必须填写价格")
        else:
            if self.price_min is None or self.price_max is None:
                raise ValueError("价格区间模式下必须填写价格上下限")
            if self.price_min > self.price_max:
                raise ValueError("价格区间下限不能大于上限")
        return self


__all__ = [
    "MATERIAL_IMAGE_MAX_COUNT",
    "AiListingConfigRequest",
    "AiListingMaterialDefaults",
    "AiListingModelListRequest",
    "AiListingTaskCreateRequest",
]

