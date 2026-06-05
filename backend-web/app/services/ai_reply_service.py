"""
AI回复设置服务

功能：
1. 管理账号的AI回复配置
2. 存储在账号metadata JSON中
3. 支持模型名称、API密钥、折扣设置等
"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.services.ai_provider_service import (
    DEFAULT_AI_BASE_URL,
    DEFAULT_AI_PROVIDER_TYPE,
    clean_ai_text,
    get_ai_settings_missing_fields,
    normalize_ai_provider_type,
    read_ai_enabled,
)
from common.models.xy_account import XYAccount

DEFAULT_AI_SETTINGS = {
    "ai_enabled": False,
    "provider_type": DEFAULT_AI_PROVIDER_TYPE,
    "model_name": "qwen-plus",
    "api_key": "",
    "base_url": DEFAULT_AI_BASE_URL,
    "max_discount_percent": 10,
    "max_discount_amount": 100,
    "max_bargain_rounds": 3,
    "custom_prompts": "",
    "ai_time_range_start": "",
    "ai_time_range_end": "",
}


class AIReplySettingsService:
    """Stores AI reply settings within the XYAccount metadata JSON blob."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _extract_settings(self, account: XYAccount) -> dict:
        stored = (account.metadata_json or {}).get("ai_reply_settings") or {}
        payload = DEFAULT_AI_SETTINGS.copy()
        payload.update({k: v for k, v in stored.items() if v is not None})
        payload["ai_enabled"] = read_ai_enabled(stored)
        payload["max_discount_percent"] = int(payload.get("max_discount_percent", 10) or 0)
        payload["max_discount_amount"] = int(payload.get("max_discount_amount", 100) or 0)
        payload["max_bargain_rounds"] = int(payload.get("max_bargain_rounds", 3) or 0)
        payload["provider_type"] = normalize_ai_provider_type(
            payload.get("provider_type"),
            payload.get("base_url"),
            payload.get("model_name"),
        )
        payload["model_name"] = clean_ai_text(payload.get("model_name"))
        payload["api_key"] = clean_ai_text(payload.get("api_key"))
        payload["base_url"] = clean_ai_text(payload.get("base_url"))
        payload["custom_prompts"] = payload.get("custom_prompts") or ""
        payload["ai_time_range_start"] = payload.get("ai_time_range_start") or ""
        payload["ai_time_range_end"] = payload.get("ai_time_range_end") or ""
        return payload

    async def get_settings(self, account: XYAccount) -> dict:
        return self._extract_settings(account)

    async def update_settings(self, account: XYAccount, payload: dict) -> dict:
        # 先获取现有设置，然后合并新的设置
        existing = self._extract_settings(account)
        
        # 只更新payload中明确提供的字段
        merged = existing.copy()
        if "ai_enabled" in payload:
            merged["ai_enabled"] = bool(payload.get("ai_enabled"))
        elif "enabled" in payload:
            merged["ai_enabled"] = bool(payload.get("enabled"))
        if "provider_type" in payload:
            merged["provider_type"] = normalize_ai_provider_type(
                payload.get("provider_type"),
                payload.get("base_url") or merged.get("base_url"),
                payload.get("model_name") or merged.get("model_name"),
            )
        if "model_name" in payload:
            merged["model_name"] = clean_ai_text(payload.get("model_name"))
        if "api_key" in payload:
            merged["api_key"] = clean_ai_text(payload.get("api_key"))
        if "base_url" in payload:
            merged["base_url"] = clean_ai_text(payload.get("base_url"))
        if "max_discount_percent" in payload:
            merged["max_discount_percent"] = int(payload.get("max_discount_percent", 10) or 0)
        if "max_discount_amount" in payload:
            merged["max_discount_amount"] = int(payload.get("max_discount_amount", 100) or 0)
        if "max_bargain_rounds" in payload:
            merged["max_bargain_rounds"] = int(payload.get("max_bargain_rounds", 3) or 0)
        if "custom_prompts" in payload:
            merged["custom_prompts"] = payload.get("custom_prompts") or ""
        if "ai_time_range_start" in payload:
            merged["ai_time_range_start"] = payload.get("ai_time_range_start") or ""
        if "ai_time_range_end" in payload:
            merged["ai_time_range_end"] = payload.get("ai_time_range_end") or ""
        merged["provider_type"] = normalize_ai_provider_type(
            merged.get("provider_type"),
            merged.get("base_url"),
            merged.get("model_name"),
        )
        if merged.get("ai_enabled"):
            missing_fields = get_ai_settings_missing_fields(merged)
            if missing_fields:
                raise ValueError(f"AI配置未填写完整，请先补全：{'、'.join(missing_fields)}")
        merged["enabled"] = merged["ai_enabled"]
        
        metadata = dict(account.metadata_json or {})
        metadata["ai_reply_settings"] = merged
        stmt = (
            update(XYAccount)
            .where(XYAccount.id == account.id)
            .values(metadata_json=metadata)
        )
        await self.session.execute(stmt)
        await self.session.commit()
        account.metadata_json = metadata
        return merged

    async def list_settings(self, owner_id: int) -> dict[str, dict]:
        stmt = select(XYAccount).where(XYAccount.owner_id == owner_id)
        result = await self.session.execute(stmt)
        accounts = result.scalars().all()
        return {account.account_id: self._extract_settings(account) for account in accounts}
