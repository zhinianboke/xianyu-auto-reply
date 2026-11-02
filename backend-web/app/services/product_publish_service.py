"""
商品发布业务逻辑服务

功能：
1. 素材库 CRUD（创建/查询/更新/删除商品模板）
2. 提供素材字典转换工具，供发布执行链路复用
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.xianyu_item_snapshot import as_bool
from app.services.xianyu_direct_payload import DirectPublishError, build_sku_payload
from common.models.data_dictionary import XYDataDictionary
from common.models.product_material import ProductMaterial
from common.services.product_material_price import (
    MATERIAL_PRICE_MODE_DICTIONARY,
    MaterialPriceError,
    ensure_unique_random_prices_available,
    normalize_material_price_fields,
)
from common.utils.time_utils import safe_isoformat


# ==================== 素材库服务 ====================


class MaterialValidationError(ValueError):
    """商品素材不符合保存规则。"""


class MaterialSpecificationError(MaterialValidationError):
    """商品素材规格不符合保存规则。"""


def _normalize_specifications(value: Any) -> list[dict]:
    """规范化规格 JSON，确保规格值名称和图片字段完整保存。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise MaterialSpecificationError("商品规格格式不正确")
    if len(value) > 2:
        raise MaterialSpecificationError("商品规格类型最多只能有2个")
    normalized: list[dict] = []
    seen_names: set[str] = set()
    for index, specification in enumerate(value, 1):
        if not isinstance(specification, dict):
            raise MaterialSpecificationError(f"第 {index} 个规格格式不正确")
        name = str(specification.get("name") or "").strip()
        if not name:
            raise MaterialSpecificationError(f"第 {index} 个规格名称不能为空")
        if name in seen_names:
            raise MaterialSpecificationError(f"规格名称重复：{name}")
        seen_names.add(name)
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
        if not values:
            raise MaterialSpecificationError(f"规格“{name}”至少需要一个规格值")
        normalized.append({
            "name": name,
            "support_image": bool(specification.get("support_image")),
            "values": values,
        })
    return normalized


def _normalize_sku_rows(
    value: Any,
    fallback_price: float | None = None,
    fallback_price_max: float | None = None,
    random_mode: bool = False,
) -> list[dict]:
    """规范化 SKU JSON；随机模式校验并保存每个规格自己的价格区间。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise MaterialSpecificationError("商品规格组合格式不正确")
    if len(value) > 200:
        raise MaterialSpecificationError("商品规格组合最多只能有200组")
    normalized: list[dict] = []
    for index, row in enumerate(value, 1):
        if not isinstance(row, dict):
            raise MaterialSpecificationError(f"第 {index} 个 SKU 格式不正确")
        specs = row.get("specs") if isinstance(row.get("specs"), dict) else {}
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            price = float(fallback_price or 0)
        if not isfinite(price) or price <= 0:
            if fallback_price is None:
                raise MaterialSpecificationError(f"第 {index} 个 SKU 价格必须大于0")
            price = float(fallback_price)
        try:
            stock_value = Decimal(str(row.get("stock")))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise MaterialSpecificationError(f"第 {index} 个 SKU 库存格式不正确") from exc
        if not stock_value.is_finite() or stock_value != stock_value.to_integral_value():
            raise MaterialSpecificationError(f"第 {index} 个 SKU 库存必须是整数")
        stock = int(stock_value)
        if stock < 0 or stock > 999999:
            raise MaterialSpecificationError(f"第 {index} 个 SKU 库存必须在0到999999之间")
        normalized_row = {
            "specs": {str(key): str(item) for key, item in specs.items()},
            "price": price,
            "stock": stock,
        }
        if random_mode:
            try:
                price_min = Decimal(str(row.get("price_min") if row.get("price_min") is not None else fallback_price)).quantize(Decimal("0.01"))
                price_max = Decimal(str(row.get("price_max") if row.get("price_max") is not None else fallback_price_max)).quantize(Decimal("0.01"))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise MaterialSpecificationError(f"第 {index} 个 SKU 随机价格区间格式不正确") from exc
            if not price_min.is_finite() or price_min <= 0:
                raise MaterialSpecificationError(f"第 {index} 个 SKU 随机价格最小值必须大于0")
            if not price_max.is_finite() or price_max <= 0:
                raise MaterialSpecificationError(f"第 {index} 个 SKU 随机价格最大值必须大于0")
            if price_min > price_max:
                raise MaterialSpecificationError(f"第 {index} 个 SKU 随机价格最小值不能大于最大值")
            normalized_row["price"] = float(price_min)
            normalized_row["price_min"] = float(price_min)
            normalized_row["price_max"] = float(price_max)
        normalized.append(normalized_row)
    return normalized


def _validate_specification_matrix(specifications: list[dict], sku_rows: list[dict]) -> None:
    """复用发布载荷校验，禁止保存缺失、重复或不完整的规格组合。"""
    try:
        build_sku_payload({"specifications": specifications, "sku_rows": sku_rows})
    except DirectPublishError as exc:
        raise MaterialSpecificationError(str(exc)) from exc


def _normalize_material_json(
    data: dict,
    fallback_price: float | None = None,
    fallback_price_max: float | None = None,
    random_mode: bool = False,
) -> dict:
    """统一处理素材中嵌套 JSON，避免 Pydantic/ORM 转换时丢字段。"""
    normalized = dict(data)
    normalized["specifications"] = _normalize_specifications(data.get("specifications"))
    normalized["sku_rows"] = _normalize_sku_rows(
        data.get("sku_rows"),
        fallback_price=fallback_price,
        fallback_price_max=fallback_price_max,
        random_mode=random_mode,
    )
    normalized["platform_category_path"] = data.get("platform_category_path") or []
    normalized["platform_attributes"] = data.get("platform_attributes") or []
    normalized["videos"] = data.get("videos") or []
    normalized["images"] = data.get("images") or []
    return normalized


def _normalize_material_data(data: dict, current: ProductMaterial | None = None) -> dict:
    """统一规范化素材嵌套字段与价格配置。"""
    normalized = dict(data)
    try:
        normalized = normalize_material_price_fields(normalized, current=current)
    except MaterialPriceError as exc:
        raise MaterialValidationError(str(exc)) from exc

    random_mode = normalized["price_mode"] == "random"
    fallback_price = normalized.get("price_min") if random_mode else None
    fallback_price_max = normalized.get("price_max") if random_mode else None
    if current is None:
        normalized = _normalize_material_json(
            normalized,
            fallback_price=fallback_price,
            fallback_price_max=fallback_price_max,
            random_mode=random_mode,
        )
        specifications = normalized["specifications"]
        sku_rows = normalized["sku_rows"]
    else:
        specifications = (
            _normalize_specifications(normalized.get("specifications"))
            if "specifications" in normalized
            else _normalize_specifications(current.specifications)
        )
        sku_rows = (
            _normalize_sku_rows(
                normalized.get("sku_rows"),
                fallback_price=fallback_price,
                fallback_price_max=fallback_price_max,
                random_mode=random_mode,
            )
            if "sku_rows" in normalized
            else _normalize_sku_rows(
                current.sku_rows,
                fallback_price=fallback_price,
                fallback_price_max=fallback_price_max,
                random_mode=random_mode,
            )
        )
        if "specifications" in normalized:
            normalized["specifications"] = specifications
        if "sku_rows" in normalized:
            normalized["sku_rows"] = sku_rows
    if random_mode and sku_rows:
        try:
            ensure_unique_random_prices_available([
                (row["price_min"], row["price_max"])
                for row in sku_rows
            ])
        except MaterialPriceError as exc:
            raise MaterialSpecificationError(str(exc)) from exc
        normalized["price_min"] = min(row["price_min"] for row in sku_rows)
        normalized["price_max"] = max(row["price_max"] for row in sku_rows)
        normalized["price"] = normalized["price_min"]
    publish_sku_rows = [
        {
            "specs": row["specs"],
            "price": row["price_min"] if random_mode else row["price"],
            "stock": row["stock"],
        }
        for row in sku_rows
    ]
    _validate_specification_matrix(specifications, publish_sku_rows)
    return normalized


class ProductMaterialService:
    """商品素材库 CRUD 服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: int,
        data: dict,
    ) -> ProductMaterial:
        """创建商品素材，平台分类字段按请求原样保存。"""
        data = _normalize_material_data(data)
        shipping_method = str(data.get("shipping_method") or "free")
        material = ProductMaterial(
            user_id=user_id,
            title=data["title"],
            description=data["description"],
            price=float(data["price"]),
            price_mode=data["price_mode"],
            price_min=float(data["price_min"]) if data.get("price_min") is not None else None,
            price_max=float(data["price_max"]) if data.get("price_max") is not None else None,
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
            # delivery_method 仅为兼容展示字段，实际发布由 shipping_method 决定。
            delivery_method="pickup" if shipping_method == "none" else "express",
            shipping_method=shipping_method,
            # 兼容 API/历史调用可能传入的 "true"/"false" 字符串，避免 bool("false") 为 True。
            support_pickup=as_bool(data.get("support_pickup", False)),
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

    async def list_price_modes(self) -> List[Dict[str, str]]:
        """从数据字典读取素材价格模式选项。"""
        stmt = (
            select(XYDataDictionary.dict_value, XYDataDictionary.dict_label)
            .where(
                XYDataDictionary.dict_type == MATERIAL_PRICE_MODE_DICTIONARY,
                XYDataDictionary.enabled.is_(True),
            )
            .order_by(XYDataDictionary.sort_order.asc(), XYDataDictionary.id.asc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"value": row.dict_value, "label": row.dict_label} for row in rows]

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

    async def update(
        self,
        material_id: int,
        user_id: int = None,
        data: dict = None,
    ) -> Optional[ProductMaterial]:
        """更新素材，平台分类字段按请求原样保存。"""
        data = data or {}
        material = await self.get(material_id, user_id)
        if not material:
            return None

        data = _normalize_material_data(data, current=material)

        updatable = [
            "title", "description", "price", "price_mode", "price_min", "price_max", "original_price", "category",
            "platform_category_id", "platform_category_name",
            "platform_channel_category_id", "platform_channel_category_name",
            "platform_leaf_id", "platform_tb_category_id", "platform_category_path", "platform_attributes",
            "category_source", "category_confidence", "images", "videos", "specifications", "sku_rows", "quantity",
            "delivery_method", "shipping_method", "support_pickup", "postage", "address", "address_expected_text", "brand", "condition", "remark",
        ]
        for field in updatable:
            if field in data:
                value = data[field]
                if field in ("price", "postage"):
                    value = float(value) if value is not None else 0
                elif field in ("price_min", "price_max", "original_price"):
                    value = float(value) if value is not None else None
                elif field == "support_pickup":
                    # 兼容表单/历史调用传入的布尔字符串，避免 bool("false") 被当作 True。
                    value = as_bool(value)
                setattr(material, field, value)

        # 防止历史调用只更新 delivery_method 造成与实际运费方式不一致。
        material.delivery_method = "pickup" if material.shipping_method == "none" else "express"

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
    shipping_method = m.shipping_method or ("fixed" if m.postage else "free")
    return {
        "id": m.id,
        "user_id": m.user_id,
        "title": m.title,
        "description": m.description,
        "price": float(m.price) if m.price is not None else 0,
        "price_mode": m.price_mode or "fixed",
        "price_min": float(m.price_min) if m.price_min is not None else None,
        "price_max": float(m.price_max) if m.price_max is not None else None,
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
        # shipping_method 是实际发布依据；兼容历史记录中的旧/空 delivery_method。
        "delivery_method": "pickup" if shipping_method == "none" else "express",
        "shipping_method": shipping_method,
        "support_pickup": as_bool(m.support_pickup),
        "postage": float(m.postage) if m.postage is not None else 0,
        "address": m.address,
        "address_expected_text": m.address_expected_text,
        "brand": m.brand,
        "condition": m.condition,
        "remark": m.remark,
        "created_at": safe_isoformat(m.created_at),
        "updated_at": safe_isoformat(m.updated_at),
    }
