"""
商品发布业务逻辑服务

功能：
1. 素材库 CRUD（创建/查询/更新/删除商品模板）
2. 提供素材字典转换工具，供发布执行链路复用
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.product_material import ProductMaterial


# ==================== 素材库服务 ====================

from common.utils.time_utils import safe_isoformat


class MaterialSpecificationError(ValueError):
    """商品素材规格不符合保存规则。"""


def _normalize_specifications(value: Any) -> list[dict]:
    """规范化规格 JSON，确保规格值名称和图片字段完整保存。"""
    if not isinstance(value, list):
        return []
    normalized: list[dict] = []
    for specification in value[:2]:
        if not isinstance(specification, dict):
            continue
        name = str(specification.get("name") or "").strip()
        if not name:
            continue
        values: list[dict] = []
        seen_values: set[str] = set()
        for item in specification.get("values") or []:
            if not isinstance(item, dict):
                continue
            value_name = str(item.get("name") or "").strip()
            if not value_name:
                continue
            if value_name in seen_values:
                raise MaterialSpecificationError(f"规格“{name}”存在重复规格值：{value_name}")
            seen_values.add(value_name)
            values.append({"name": value_name, "image": item.get("image") or None})
        normalized.append({
            "name": name,
            "support_image": bool(specification.get("support_image")),
            "values": values,
        })
    return normalized


def _normalize_sku_rows(value: Any) -> list[dict]:
    """规范化 SKU JSON，保留每个规格组合的价格和库存。"""
    if not isinstance(value, list):
        return []
    normalized: list[dict] = []
    for row in value[:200]:
        if not isinstance(row, dict):
            continue
        specs = row.get("specs") if isinstance(row.get("specs"), dict) else {}
        try:
            price = float(row.get("price"))
            stock = int(row.get("stock"))
        except (TypeError, ValueError):
            continue
        if price <= 0 or stock < 0:
            continue
        normalized.append({
            "specs": {str(key): str(item) for key, item in specs.items()},
            "price": price,
            "stock": stock,
        })
    return normalized


def _normalize_material_json(data: dict) -> dict:
    """统一处理素材中嵌套 JSON，避免 Pydantic/ORM 转换时丢字段。"""
    normalized = dict(data)
    normalized["specifications"] = _normalize_specifications(data.get("specifications"))
    normalized["sku_rows"] = _normalize_sku_rows(data.get("sku_rows"))
    normalized["platform_category_path"] = data.get("platform_category_path") or []
    normalized["platform_attributes"] = data.get("platform_attributes") or []
    normalized["videos"] = data.get("videos") or []
    normalized["images"] = data.get("images") or []
    return normalized


class ProductMaterialService:
    """商品素材库 CRUD 服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: int, data: dict) -> ProductMaterial:
        """创建素材"""
        data = _normalize_material_json(data)
        material = ProductMaterial(
            user_id=user_id,
            title=data["title"],
            description=data["description"],
            price=float(data["price"]),
            original_price=float(data["original_price"]) if data.get("original_price") else None,
            category=data.get("category"),
            platform_category_id=data.get("platform_category_id"),
            platform_category_name=data.get("platform_category_name"),
            platform_channel_category_id=data.get("platform_channel_category_id"),
            platform_channel_category_name=data.get("platform_channel_category_name"),
            platform_leaf_id=data.get("platform_leaf_id"),
            platform_tb_category_id=data.get("platform_tb_category_id"),
            platform_category_path=data.get("platform_category_path") or [],
            platform_attributes=data.get("platform_attributes") or [],
            category_source=data.get("category_source") or "manual",
            category_confidence=data.get("category_confidence"),
            images=data["images"],
            videos=data.get("videos") or [],
            specifications=data["specifications"],
            sku_rows=data["sku_rows"],
            quantity=int(data.get("quantity") or 1),
            delivery_method=data.get("delivery_method", "express"),
            shipping_method=data.get("shipping_method", "free"),
            support_pickup=bool(data.get("support_pickup", False)),
            postage=float(data.get("postage", 0)),
            address=data.get("address"),
            address_expected_text=data.get("address_expected_text"),
            brand=data.get("brand"),
            condition=data.get("condition", "全新"),
            remark=data.get("remark"),
        )
        self.session.add(material)
        await self.session.commit()
        await self.session.refresh(material)
        return material

    async def list_materials(
        self, user_id: int = None, page: int = 1, page_size: int = 20,
        title: str = None, category: str = None, condition: str = None,
        platform_category_id: str = None,
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

        base_cond = [ProductMaterial.is_deleted.is_(False)]
        if user_id is not None:
            base_cond.append(ProductMaterial.user_id == user_id)
        if title:
            base_cond.append(ProductMaterial.title.ilike(f"%{title}%"))
        if category:
            base_cond.append(ProductMaterial.category == category)
        if condition:
            base_cond.append(ProductMaterial.condition == condition)
        if platform_category_id:
            base_cond.append(ProductMaterial.platform_category_id == platform_category_id)

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
        conds = [ProductMaterial.id == material_id, ProductMaterial.is_deleted.is_(False)]
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
            ProductMaterial.is_deleted.is_(False),
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

        if "specifications" in data:
            data["specifications"] = _normalize_specifications(data.get("specifications"))
        if "sku_rows" in data:
            data["sku_rows"] = _normalize_sku_rows(data.get("sku_rows"))

        updatable = [
            "title", "description", "price", "original_price", "category",
            "platform_category_id", "platform_category_name",
            "platform_channel_category_id", "platform_channel_category_name",
            "platform_leaf_id", "platform_tb_category_id", "platform_category_path", "platform_attributes",
            "category_source", "category_confidence", "images", "videos", "specifications", "sku_rows", "quantity",
            "delivery_method", "shipping_method", "support_pickup", "postage", "address", "address_expected_text", "brand", "condition", "remark",
        ]
        for field in updatable:
            if field in data:
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
        material.is_deleted = True
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
        conds = [ProductMaterial.id.in_(material_ids), ProductMaterial.is_deleted.is_(False)]
        if user_id is not None:
            conds.append(ProductMaterial.user_id == user_id)
        stmt = select(ProductMaterial).where(*conds)
        rows = (await self.session.execute(stmt)).scalars().all()
        for row in rows:
            row.is_deleted = True
        await self.session.commit()
        return len(rows)


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
        "platform_category_id": m.platform_category_id,
        "platform_category_name": m.platform_category_name,
        "platform_channel_category_id": m.platform_channel_category_id,
        "platform_channel_category_name": m.platform_channel_category_name,
        "platform_leaf_id": m.platform_leaf_id,
        "platform_tb_category_id": m.platform_tb_category_id,
        "platform_category_path": m.platform_category_path or [],
        "platform_attributes": m.platform_attributes or [],
        "category_source": m.category_source or "manual",
        "category_confidence": float(m.category_confidence) if m.category_confidence is not None else None,
        "images": m.images or [],
        "videos": m.videos or [],
        "specifications": m.specifications or [],
        "sku_rows": m.sku_rows or [],
        "quantity": m.quantity or 1,
        "delivery_method": m.delivery_method,
        "shipping_method": m.shipping_method or ("fixed" if m.postage else "free"),
        "support_pickup": bool(m.support_pickup),
        "postage": float(m.postage) if m.postage is not None else 0,
        "address": m.address,
        "address_expected_text": m.address_expected_text,
        "brand": m.brand,
        "condition": m.condition,
        "remark": m.remark,
        "created_at": safe_isoformat(m.created_at),
        "updated_at": safe_isoformat(m.updated_at),
    }
