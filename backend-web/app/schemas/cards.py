"""卡券创建、更新及关联接口请求模型。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class CardCreate(BaseModel):
    item_id: Optional[str] = None  # 关联商品ID
    name: str
    type: str  # 'api' | 'text' | 'data' | 'image'
    description: Optional[str] = None
    enabled: Optional[bool] = True
    delay_seconds: Optional[int] = 0
    use_no_logistics_form: bool = False
    price: Optional[str] = None  # 对接价格
    is_dockable: Optional[bool] = False  # 是否可对接
    fee_payer: Optional[str] = None  # 手续费支付方式：distributor/dealer
    min_price: Optional[str] = None  # 最低售价
    dock_visibility: Optional[str] = None  # 对接可见性：public/dealer_only
    is_multi_spec: Optional[bool] = False
    spec_name: Optional[str] = None
    spec_value: Optional[str] = None
    api_config: Optional[Dict[str, Any]] = None
    text_content: Optional[str] = None
    data_content: Optional[str] = None
    image_url: Optional[str] = None
    image_urls: Optional[List[str]] = None  # 多图片URL列表，最多3张


class CardUpdate(BaseModel):
    item_id: Optional[str] = None  # 关联商品ID
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    delay_seconds: Optional[int] = None
    use_no_logistics_form: Optional[bool] = None
    price: Optional[str] = None  # 对接价格
    is_dockable: Optional[bool] = None  # 是否可对接
    fee_payer: Optional[str] = None  # 手续费支付方式：distributor/dealer
    min_price: Optional[str] = None  # 最低售价
    dock_visibility: Optional[str] = None  # 对接可见性：public/dealer_only
    is_multi_spec: Optional[bool] = None
    spec_name: Optional[str] = None
    spec_value: Optional[str] = None
    api_config: Optional[Dict[str, Any]] = None
    text_content: Optional[str] = None
    data_content: Optional[str] = None
    image_url: Optional[str] = None
    image_urls: Optional[List[str]] = None  # 多图片URL列表，最多3张


class BatchDeleteRequest(BaseModel):
    ids: List[int]


class BatchSaveCardRequest(BaseModel):
    """批量保存卡券请求"""
    item_ids: List[str]
    name: str
    type: str
    description: Optional[str] = None
    enabled: Optional[bool] = True
    delay_seconds: Optional[int] = 0
    use_no_logistics_form: bool = False
    price: Optional[str] = None  # 对接价格
    is_dockable: Optional[bool] = False  # 是否可对接
    fee_payer: Optional[str] = None  # 手续费支付方式：distributor/dealer
    min_price: Optional[str] = None  # 最低售价
    dock_visibility: Optional[str] = None  # 对接可见性：public/dealer_only
    is_multi_spec: Optional[bool] = False
    spec_name: Optional[str] = None
    spec_value: Optional[str] = None
    api_config: Optional[Dict[str, Any]] = None
    text_content: Optional[str] = None
    data_content: Optional[str] = None
    image_url: Optional[str] = None
    image_urls: Optional[List[str]] = None  # 多图片URL列表，最多3张


class BatchClearItemRelationsRequest(BaseModel):
    """批量清空商品的卡券关联关系"""
    item_ids: List[str]


class BatchBindRequest(BaseModel):
    """批量绑定卡券到商品（多对多关联表方式）"""
    card_ids: List[int]
    item_ids: List[str]


class UpdateCardItemsRequest(BaseModel):
    """更新卡券关联的商品列表"""
    item_ids: List[str]


class CardRelationItem(BaseModel):
    """单条卡券关联信息"""
    card_id: int
    source: str = "own"  # own/dock_l1/dock_l2
    dock_record_id: Optional[int] = None

class UpdateItemCardsRequest(BaseModel):
    """更新商品关联的卡券列表"""
    card_items: List[CardRelationItem]
