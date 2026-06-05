from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AIReplySettings(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    ai_enabled: bool = False
    provider_type: str = "openai_compatible"
    model_name: str = "qwen-plus"
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    max_discount_percent: int = 10
    max_discount_amount: int = 100
    max_bargain_rounds: int = 3
    custom_prompts: str = ""
    ai_time_range_start: str = ""
    ai_time_range_end: str = ""


class AIReplySettingsUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    ai_enabled: bool | None = None
    provider_type: str | None = None
    model_name: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    max_discount_percent: int | None = None
    max_discount_amount: int | None = None
    max_bargain_rounds: int | None = None
    custom_prompts: str | None = None
    enabled: bool | None = None
    ai_time_range_start: str | None = None
    ai_time_range_end: str | None = None


class AIModelListRequest(BaseModel):
    provider_type: str = "openai_compatible"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key: str = ""
