from __future__ import annotations

from pydantic import BaseModel, Field


class KeywordDetail(BaseModel):
    id: str | None = None
    keyword: str
    reply: str
    item_id: str | None = Field(default=None)
    type: str = Field(default="text")
    image_url: str | None = None
    item_title: str | None = None
    account_id: str | None = None  # 账号ID，查询全部账号时返回


class KeywordTextPayload(BaseModel):
    keyword: str
    reply: str | None = ""
    item_id: str | None = None


class KeywordTextUpdatePayload(BaseModel):
    account_id: str
    keyword: str
    reply: str | None = ""
    item_id: str | None = None


class KeywordTextList(BaseModel):
    keywords: list[KeywordTextPayload]
