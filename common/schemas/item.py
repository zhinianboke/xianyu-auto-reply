from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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

