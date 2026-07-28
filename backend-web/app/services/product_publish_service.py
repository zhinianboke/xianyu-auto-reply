"""
商品发布业务逻辑服务

功能：
1. 素材库 CRUD（创建/查询/更新/删除商品模板）
2. 提供素材字典转换工具，供发布执行链路复用
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.product_material import ProductMaterial


# ==================== 素材库服务 ====================

from common.utils.time_utils import safe_isoformat


def _comparable_material_titles(title: str) -> List[str]:
    """返回用于同名判断的标题，兼容 Gamer520 自动添加的“秒发”前缀。"""
    normalized = re.sub(r"\s+", " ", str(title or "")).strip()
    without_prefix = re.sub(r"^【秒发】\s*", "", normalized).strip()
    return list(
        dict.fromkeys(
            value
            for value in (normalized, without_prefix)
            if value
        )
    )


class ProductMaterialService:
    """商品素材库 CRUD 服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: int, data: dict) -> ProductMaterial:
        """创建素材"""
        material = ProductMaterial(
            user_id=user_id,
            title=data["title"],
            description=data["description"],
            price=float(data["price"]),
            original_price=float(data["original_price"]) if data.get("original_price") else None,
            category=data.get("category"),
            images=data.get("images", []),
            delivery_method=data.get("delivery_method", "express"),
            postage=float(data.get("postage", 0)),
            address=data.get("address"),
            brand=data.get("brand"),
            condition=data.get("condition", "全新"),
            remark=data.get("remark"),
        )
        self.session.add(material)
        await self.session.commit()
        await self.session.refresh(material)
        return material

    async def upsert_external(
        self,
        user_id: int,
        source_type: str,
        items: List[dict],
    ) -> List[dict]:
        """按外部来源商品ID批量幂等创建或更新素材。"""
        results: List[dict] = []
        for item in items:
            external_id = str(item["external_id"])
            stmt = select(ProductMaterial).where(
                ProductMaterial.user_id == user_id,
                ProductMaterial.source_type == source_type,
                ProductMaterial.source_item_id == external_id,
            )
            material = (await self.session.execute(stmt)).scalar_one_or_none()

            if material is None:
                comparable_titles = _comparable_material_titles(item["title"])
                duplicate_stmt = (
                    select(ProductMaterial)
                    .where(
                        ProductMaterial.user_id == user_id,
                        func.trim(ProductMaterial.title).in_(comparable_titles),
                    )
                    .order_by(ProductMaterial.id.asc())
                )
                duplicate = (
                    await self.session.execute(duplicate_stmt)
                ).scalars().first()
                if duplicate is not None:
                    results.append(
                        {
                            "external_id": external_id,
                            "material_id": duplicate.id,
                            "action": "skipped",
                            "content_hash": duplicate.source_content_hash,
                            "reason": "素材库已存在同名商品",
                        }
                    )
                    continue

                material = ProductMaterial(
                    user_id=user_id,
                    title=item["title"],
                    description=item["description"],
                    price=float(item["price"]),
                    original_price=None,
                    category=item.get("category"),
                    images=item.get("images", []),
                    delivery_method=item.get("delivery_method", "express"),
                    postage=float(item.get("postage", 0)),
                    address=item.get("address"),
                    brand=item.get("brand"),
                    condition=item.get("condition", "全新"),
                    remark=item.get("remark"),
                    source_type=source_type,
                    source_item_id=external_id,
                    source_content_hash=item["content_hash"],
                )
                self.session.add(material)
                await self.session.flush()
                action = "created"
            elif material.source_content_hash == item["content_hash"]:
                action = "unchanged"
            else:
                material.title = item["title"]
                material.description = item["description"]
                material.price = float(item["price"])
                material.category = item.get("category")
                material.images = item.get("images", [])
                material.delivery_method = item.get("delivery_method", "express")
                material.postage = float(item.get("postage", 0))
                material.address = item.get("address")
                material.brand = item.get("brand")
                material.condition = item.get("condition", "全新")
                material.remark = item.get("remark")
                material.source_content_hash = item["content_hash"]
                action = "updated"

            results.append(
                {
                    "external_id": external_id,
                    "material_id": material.id,
                    "action": action,
                    "content_hash": material.source_content_hash,
                }
            )

        await self.session.commit()
        return results

    async def list_materials(
        self, user_id: int = None, page: int = 1, page_size: int = 20,
        title: str = None, category: str = None, condition: str = None,
    ) -> Dict[str, Any]:
        """分页查询素材列表
        
        Args:
            user_id: 用户ID，为None时查询全部（管理员场景）
            title: 标题模糊搜索
            category: 分类筛选
            condition: 成色筛选
        """
        page = max(page, 1)
        page_size = page_size if page_size in (10, 20, 50, 100, 500, 1000) else 20

        base_cond = []
        if user_id is not None:
            base_cond.append(ProductMaterial.user_id == user_id)
        if title:
            base_cond.append(ProductMaterial.title.ilike(f"%{title}%"))
        if category:
            base_cond.append(ProductMaterial.category == category)
        if condition:
            base_cond.append(ProductMaterial.condition == condition)

        count_stmt = (
            select(func.count())
            .select_from(ProductMaterial)
            .where(*base_cond)
        )
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(ProductMaterial)
            .where(*base_cond)
            .order_by(desc(ProductMaterial.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        return {
            "list": [_material_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }

    async def get(self, material_id: int, user_id: int = None) -> Optional[ProductMaterial]:
        """查询单条素材
        
        Args:
            material_id: 素材ID
            user_id: 用户ID，为None时不限用户（管理员场景）
        """
        conds = [ProductMaterial.id == material_id]
        if user_id is not None:
            conds.append(ProductMaterial.user_id == user_id)
        stmt = select(ProductMaterial).where(*conds)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_by_ids(self, material_ids: List[int], user_id: int) -> List[ProductMaterial]:
        if not material_ids:
            return []
        unique_ids = list(dict.fromkeys(material_ids))
        stmt = select(ProductMaterial).where(
            ProductMaterial.user_id == user_id,
            ProductMaterial.id.in_(unique_ids),
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        material_map = {row.id: row for row in rows}
        return [material_map[mid] for mid in material_ids if mid in material_map]

    async def update(self, material_id: int, user_id: int = None, data: dict = None) -> Optional[ProductMaterial]:
        """更新素材（user_id=None时管理员可操作任意素材）"""
        data = data or {}
        material = await self.get(material_id, user_id)
        if not material:
            return None

        updatable = [
            "title", "description", "price", "original_price", "category",
            "images", "delivery_method", "postage", "address", "brand",
            "condition", "remark",
        ]
        for field in updatable:
            if field in data and data[field] is not None:
                value = data[field]
                if field in ("price", "original_price", "postage"):
                    value = float(value) if value else (None if field == "original_price" else 0)
                setattr(material, field, value)

        await self.session.commit()
        await self.session.refresh(material)
        return material

    async def delete(self, material_id: int, user_id: int = None) -> bool:
        """删除素材（user_id=None时管理员可操作任意素材）"""
        material = await self.get(material_id, user_id)
        if not material:
            return False
        await self.session.delete(material)
        await self.session.commit()
        return True

    async def batch_delete(self, material_ids: List[int], user_id: int = None) -> int:
        """批量删除素材，返回实际删除数量
        
        Args:
            material_ids: 素材ID列表
            user_id: 用户ID，为None时管理员可操作任意素材
        """
        if not material_ids:
            return 0
        from sqlalchemy import delete as sa_delete
        conds = [ProductMaterial.id.in_(material_ids)]
        if user_id is not None:
            conds.append(ProductMaterial.user_id == user_id)
        stmt = sa_delete(ProductMaterial).where(*conds)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount


# ==================== 工具函数 ====================

def _material_to_dict(m: ProductMaterial) -> dict:
    """将素材模型转为字典"""
    return {
        "id": m.id,
        "user_id": m.user_id,
        "title": m.title,
        "description": m.description,
        "price": float(m.price) if m.price is not None else 0,
        "original_price": float(m.original_price) if m.original_price is not None else None,
        "category": m.category,
        "images": m.images or [],
        "delivery_method": m.delivery_method,
        "postage": float(m.postage) if m.postage is not None else 0,
        "address": m.address,
        "brand": m.brand,
        "condition": m.condition,
        "remark": m.remark,
        "source_type": m.source_type,
        "source_item_id": m.source_item_id,
        "source_content_hash": m.source_content_hash,
        "created_at": safe_isoformat(m.created_at),
        "updated_at": safe_isoformat(m.updated_at),
    }
