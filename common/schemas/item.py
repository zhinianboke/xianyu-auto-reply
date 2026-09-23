from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ItemTarget(BaseModel):
    # cookie_id 允许为空/None：账号已删除的孤儿商品在列表中 cookie_id 为 null，
    # 批量删除时原样回传，需接受 None 以便路由按商品ID删除（见 batch_delete_items）。
    cookie_id: str | None = None
    item_id: str


class ItemBatchDeleteRequest(BaseModel):
    items: list[ItemTarget]


class ItemBatchOfflineRequest(BaseModel):
    """批量下架请求：使用指定账号的Cookie下架其名下的商品。"""

    cookie_id: str
    item_ids: list[str]


class ItemReplyUpdate(BaseModel):
    reply: str


class ItemPageFetchRequest(BaseModel):
    cookie_id: str
    page: int | None = Field(default=None, ge=1)
    page_number: int | None = Field(default=None, ge=1)
    page_size: int | None = Field(default=None, ge=1, le=100)
    size: int | None = Field(default=None, ge=1, le=100)

    model_config = ConfigDict(extra="ignore")


class ItemFullFetchRequest(BaseModel):
    cookie_id: str | None = None
    page_size: int | None = Field(default=None, ge=1, le=100)
    max_pages: int | None = Field(default=None, ge=1)

    model_config = ConfigDict(extra="ignore")


class SellerItemAttribute(BaseModel):
    """闲鱼平台属性标签（成色/品牌等），字段与商品发布保持一致。"""

    property_id: str | None = Field(default=None, max_length=64)
    property_name: str | None = Field(default=None, max_length=100)
    value_id: str | None = Field(default=None, max_length=64)
    value_name: str | None = Field(default=None, max_length=200)
    text: str | None = Field(default=None, max_length=200)
    properties: str | None = Field(default=None, max_length=500)


class SellerItemSpecificationValue(BaseModel):
    """单个规格值。"""

    name: str = Field(..., min_length=1, max_length=100)
    image: str | None = Field(default=None, max_length=2000)


class SellerItemSpecification(BaseModel):
    """规格类型及其可选值。"""

    name: str = Field(..., min_length=1, max_length=100)
    values: list[SellerItemSpecificationValue] = Field(default_factory=list, max_length=50)
    support_image: bool = False


class SellerItemSkuRow(BaseModel):
    """规格组合对应的价格与库存。"""

    specs: dict[str, str] = Field(default_factory=dict, max_length=4)
    price: float = Field(..., gt=0)
    stock: int = Field(default=0, ge=0, le=999999)


class SellerItemVideo(BaseModel):
    """商品视频（平台已有视频或新上传视频）。

    平台已有视频携带 file_id（= mediaCloudFileId），提交时后端凭它匹配快照原样回传，
    不重复上传；新上传视频携带 url/path 指向本地素材，由后端走上传链路。
    """

    url: str | None = Field(default=None, max_length=2000)
    path: str | None = Field(default=None, max_length=500)
    name: str | None = Field(default=None, max_length=200)
    size: int | None = Field(default=None, ge=0)
    file_id: str | None = Field(default=None, max_length=128)
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="ignore")


class SellerItemEditRequest(BaseModel):
    """鱼小铺商品编辑请求，字段与单品发布请求保持一致（不含账号ID）。"""

    title: str = Field(..., min_length=1, max_length=200)
    # 编辑是全量覆盖：平台已有描述可能超过发布表单的 1500 字限制，
    # 若沿用更严的上限，未改描述的商品会被本地校验直接卡住而无法保存
    description: str = Field(..., min_length=1, max_length=5000)
    price: float = Field(..., gt=0)
    original_price: float | None = None
    images: list[str] = Field(..., min_length=1, max_length=9)
    # 编辑弹窗会回填平台已有视频；空列表表示用户删光了视频（后端不再回退快照）
    videos: list[SellerItemVideo] = Field(default_factory=list, max_length=3)
    platform_category_id: str | None = Field(default=None, max_length=64)
    platform_category_name: str | None = Field(default=None, max_length=100)
    platform_channel_category_id: str | None = Field(default=None, max_length=64)
    platform_channel_category_name: str | None = Field(default=None, max_length=100)
    platform_leaf_id: str | None = Field(default=None, max_length=64)
    platform_tb_category_id: str | None = Field(default=None, max_length=64)
    platform_attributes: list[SellerItemAttribute] = Field(default_factory=list, max_length=30)
    specifications: list[SellerItemSpecification] = Field(default_factory=list, max_length=2)
    sku_rows: list[SellerItemSkuRow] = Field(default_factory=list, max_length=200)
    # 允许 0：平台售罄商品的库存就是 0，强制改成 1 会把商品重新放量
    quantity: int = Field(default=1, ge=0, le=999999)
    address: str | None = Field(default=None, max_length=200)
    address_expected_text: str | None = Field(default=None, max_length=200)
    delivery_method: str = Field(
        default="express", pattern="^(express|pickup)$", description="发货方式：express/pickup"
    )
    shipping_method: str = Field(default="free", pattern="^(free|distance|fixed|template|none)$")
    support_pickup: bool = False
    postage: float = Field(default=0, ge=0, le=1000, description="邮费，0表示包邮")
    brand: str | None = Field(default=None, max_length=100)
    condition: str | None = Field(default=None, max_length=20)

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def normalize_delivery_method(self) -> "SellerItemEditRequest":
        """以实际运费方式统一兼容字段，避免编辑载荷自相矛盾。"""
        self.delivery_method = "pickup" if self.shipping_method == "none" else "express"
        return self

