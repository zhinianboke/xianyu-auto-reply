"""
AI 铺货配置服务

功能：
1. AI 铺货配置的增删改查（按 owner_id 隔离，删除走软删除）
2. 密钥脱敏输出，接口不把明文密钥回传给前端
3. 更新时支持"密钥留空表示不修改"，避免前端必须回传明文
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.ai_listing_config import AiListingConfig
from common.utils.time_utils import safe_isoformat

# 分页大小白名单，与素材库列表保持一致
ALLOWED_PAGE_SIZES = (10, 20, 50, 100)

# 需要脱敏的密钥字段
SECRET_FIELDS = ("text_api_key", "image_api_key")


def mask_secret(value: Optional[str]) -> str:
    """把密钥脱敏成可展示的形式

    Args:
        value: 原始密钥，可为空。
    Returns:
        形如 ``sk-****1234`` 的脱敏串；空值返回空字符串。
    """
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return f"{text[:3]}****{text[-4:]}"


def config_to_dict(config: AiListingConfig) -> Dict[str, Any]:
    """把配置 ORM 对象转成接口返回的字典（密钥已脱敏）

    Args:
        config: 配置 ORM 对象。
    Returns:
        供前端展示的字典，额外带 ``has_image_api_key`` 标记密钥是否已配置。
    """
    return {
        "id": config.id,
        "name": config.name,
        "provider_type": config.provider_type,
        "text_base_url": config.text_base_url,
        "text_api_key_masked": mask_secret(config.text_api_key),
        "text_model": config.text_model,
        "text_temperature": float(config.text_temperature or 0),
        "text_max_tokens": config.text_max_tokens,
        "prompt_template": config.prompt_template or "",
        "image_enabled": bool(config.image_enabled),
        "image_base_url": config.image_base_url or "",
        "image_api_key_masked": mask_secret(config.image_api_key),
        "has_image_api_key": bool((config.image_api_key or "").strip()),
        "image_model": config.image_model or "",
        "image_size": config.image_size,
        "image_count": config.image_count,
        "created_at": safe_isoformat(config.created_at),
        "updated_at": safe_isoformat(config.updated_at),
    }


class AiListingConfigService:
    """AI 铺货配置 CRUD 服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, owner_id: int, data: Dict[str, Any]) -> AiListingConfig:
        """创建配置

        Args:
            owner_id: 归属用户ID。
            data: 已通过 Pydantic 校验的配置字段。
        Returns:
            新建的配置对象。
        """
        config = AiListingConfig(
            owner_id=owner_id,
            name=data["name"].strip(),
            provider_type=data.get("provider_type") or "openai_compatible",
            text_base_url=data["text_base_url"].strip(),
            text_api_key=data["text_api_key"].strip(),
            text_model=data["text_model"].strip(),
            text_temperature=Decimal(str(data.get("text_temperature", 0.7))),
            text_max_tokens=int(data.get("text_max_tokens") or 2048),
            prompt_template=(data.get("prompt_template") or "").strip() or None,
            image_enabled=bool(data.get("image_enabled")),
            image_base_url=(data.get("image_base_url") or "").strip() or None,
            image_api_key=(data.get("image_api_key") or "").strip() or None,
            image_model=(data.get("image_model") or "").strip() or None,
            image_size=data.get("image_size") or "1024x1024",
            image_count=int(data.get("image_count") or 1),
        )
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def list_configs(
        self, owner_id: int, page: int = 1, page_size: int = 20, name: Optional[str] = None
    ) -> Dict[str, Any]:
        """分页查询配置列表

        Args:
            owner_id: 归属用户ID。
            page: 页码，从 1 开始。
            page_size: 每页条数，不在白名单内时回落 20。
            name: 配置名称模糊搜索。
        Returns:
            ``{"list", "total", "page", "page_size", "total_pages"}``
        """
        page = max(page, 1)
        if page_size not in ALLOWED_PAGE_SIZES:
            page_size = 20

        conditions = [
            AiListingConfig.owner_id == owner_id,
            AiListingConfig.is_deleted.is_(False),
        ]
        if name:
            conditions.append(AiListingConfig.name.ilike(f"%{name}%"))

        total = await self.session.scalar(
            select(func.count()).select_from(AiListingConfig).where(*conditions)
        ) or 0

        result = await self.session.execute(
            select(AiListingConfig)
            .where(*conditions)
            .order_by(desc(AiListingConfig.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        configs = result.scalars().all()

        return {
            "list": [config_to_dict(item) for item in configs],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }

    async def get(self, config_id: int, owner_id: int) -> Optional[AiListingConfig]:
        """按ID查询单个配置（带用户隔离与软删除过滤）

        Args:
            config_id: 配置ID。
            owner_id: 归属用户ID。
        Returns:
            配置对象，不存在或不属于该用户时返回 None。
        """
        result = await self.session.execute(
            select(AiListingConfig).where(
                AiListingConfig.id == config_id,
                AiListingConfig.owner_id == owner_id,
                AiListingConfig.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self, config_id: int, owner_id: int, data: Dict[str, Any]
    ) -> Optional[AiListingConfig]:
        """更新配置

        密钥字段传空字符串表示保留原值，避免前端必须回传明文密钥。

        Args:
            config_id: 配置ID。
            owner_id: 归属用户ID。
            data: 已通过 Pydantic 校验的配置字段。
        Returns:
            更新后的配置对象，配置不存在时返回 None。
        """
        config = await self.get(config_id, owner_id)
        if not config:
            return None

        config.name = data["name"].strip()
        config.provider_type = data.get("provider_type") or "openai_compatible"
        config.text_base_url = data["text_base_url"].strip()
        config.text_model = data["text_model"].strip()
        config.text_temperature = Decimal(str(data.get("text_temperature", 0.7)))
        config.text_max_tokens = int(data.get("text_max_tokens") or 2048)
        config.prompt_template = (data.get("prompt_template") or "").strip() or None
        config.image_enabled = bool(data.get("image_enabled"))
        config.image_base_url = (data.get("image_base_url") or "").strip() or None
        config.image_model = (data.get("image_model") or "").strip() or None
        config.image_size = data.get("image_size") or "1024x1024"
        config.image_count = int(data.get("image_count") or 1)

        # 密钥留空 = 不修改
        for field in SECRET_FIELDS:
            new_value = (data.get(field) or "").strip()
            if new_value:
                setattr(config, field, new_value)

        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def delete(self, config_id: int, owner_id: int) -> bool:
        """软删除配置（保留历史数据，不做物理删除）

        Args:
            config_id: 配置ID。
            owner_id: 归属用户ID。
        Returns:
            是否删除成功（配置不存在时返回 False）。
        """
        config = await self.get(config_id, owner_id)
        if not config:
            return False
        config.is_deleted = True
        await self.session.commit()
        return True


