"""
商品素材价格模式公共服务。

功能：
1. 校验并规范化素材的固定价格 / 随机价格配置
2. 在随机价格区间内按“分”生成发布价格
3. 多规格素材按每个规格自己的区间独立随机，库存保持不变
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from secrets import randbelow
from typing import Any


MATERIAL_PRICE_MODE_DICTIONARY = "product_material_price_mode"
PRICE_MODE_FIXED = "fixed"
PRICE_MODE_RANDOM = "random"
VALID_PRICE_MODES = {PRICE_MODE_FIXED, PRICE_MODE_RANDOM}
PRICE_QUANT = Decimal("0.01")


class MaterialPriceError(ValueError):
    """素材价格模式或价格区间不符合业务规则。"""


def _read_value(source: Any, field: str) -> Any:
    """兼容从字典或 ORM 对象读取价格字段。"""
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(field)
    return getattr(source, field, None)


def _parse_price(value: Any, field_label: str) -> Decimal:
    """把价格转换为大于零且保留两位小数的 Decimal。"""
    try:
        price = Decimal(str(value)).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MaterialPriceError(f"{field_label}格式不正确") from exc
    if not price.is_finite() or price <= 0:
        raise MaterialPriceError(f"{field_label}必须大于0")
    return price


def _assign_unique_random_cents(ranges: list[tuple[int, int]]) -> list[int]:
    """为多个闭区间分配互不重复的随机分值。"""
    price_owners: dict[int, int] = {}
    row_prices: dict[int, int] = {}

    def assign(row_index: int, seen_prices: set[int]) -> bool:
        minimum, maximum = ranges[row_index]
        range_size = maximum - minimum + 1
        start = randbelow(range_size)
        probe_count = min(range_size, len(price_owners) + 1)
        for offset in range(probe_count):
            candidate = minimum + ((start + offset) % range_size)
            if candidate not in price_owners:
                old_price = row_prices.get(row_index)
                if old_price is not None:
                    price_owners.pop(old_price, None)
                price_owners[candidate] = row_index
                row_prices[row_index] = candidate
                return True

        # 没有空闲价格时，区间长度最多等于已分配规格数，可安全遍历并尝试增广换位。
        for offset in range(range_size):
            candidate = minimum + ((start + offset) % range_size)
            if candidate in seen_prices:
                continue
            seen_prices.add(candidate)
            owner = price_owners.get(candidate)
            if owner is None or (owner != row_index and assign(owner, seen_prices)):
                old_price = row_prices.get(row_index)
                if old_price is not None:
                    price_owners.pop(old_price, None)
                price_owners[candidate] = row_index
                row_prices[row_index] = candidate
                return True
        return False

    row_count = len(ranges)
    start_row = randbelow(row_count) if row_count else 0
    for offset in range(row_count):
        row_index = (start_row + offset) % row_count
        if not assign(row_index, set()):
            raise MaterialPriceError(
                "规格随机价格区间无法生成互不相同的价格，请调整重叠区间"
            )
    return [row_prices[index] for index in range(row_count)]


def ensure_unique_random_prices_available(
    ranges: list[tuple[Any, Any]],
) -> None:
    """校验多个规格区间能否分配出互不相同的两位小数价格。

    Args:
        ranges: 每个规格的（最小价格，最大价格）闭区间。
    Returns:
        无返回值；区间无解时抛出 MaterialPriceError。
    """
    cent_ranges: list[tuple[int, int]] = []
    for index, (raw_minimum, raw_maximum) in enumerate(ranges, 1):
        minimum = _parse_price(raw_minimum, f"第 {index} 个规格随机价格最小值")
        maximum = _parse_price(raw_maximum, f"第 {index} 个规格随机价格最大值")
        if minimum > maximum:
            raise MaterialPriceError(f"第 {index} 个规格随机价格最小值不能大于最大值")
        cent_ranges.append((int(minimum * 100), int(maximum * 100)))
    _assign_unique_random_cents(cent_ranges)


def normalize_material_price_fields(data: dict, current: Any = None) -> dict:
    """校验并补齐素材价格字段。

    Args:
        data: 创建或更新素材时提交的字段。
        current: 更新场景中的现有素材，用于合并未提交字段。
    Returns:
        已规范化的字段副本；随机价格模式保留原固定价格作为兼容值。
    """
    normalized = dict(data)
    raw_mode = data.get("price_mode") if "price_mode" in data else _read_value(current, "price_mode")
    price_mode = str(raw_mode or PRICE_MODE_FIXED).strip().lower()
    if price_mode not in VALID_PRICE_MODES:
        raise MaterialPriceError("价格模式无效，请选择固定价格或随机价格")

    if price_mode == PRICE_MODE_FIXED:
        raw_price = data.get("price") if "price" in data else _read_value(current, "price")
        fixed_price = _parse_price(raw_price, "固定价格")
        normalized.update({
            "price_mode": PRICE_MODE_FIXED,
            "price": float(fixed_price),
            "price_min": None,
            "price_max": None,
        })
        return normalized

    raw_min = data.get("price_min") if "price_min" in data else _read_value(current, "price_min")
    raw_max = data.get("price_max") if "price_max" in data else _read_value(current, "price_max")
    price_min = _parse_price(raw_min, "随机价格最小值")
    price_max = _parse_price(raw_max, "随机价格最大值")
    if price_min > price_max:
        raise MaterialPriceError("随机价格最小值不能大于最大值")
    raw_compat_price = data.get("price") if "price" in data else _read_value(current, "price")
    try:
        compat_price = _parse_price(raw_compat_price, "价格")
    except MaterialPriceError:
        compat_price = price_min
    normalized.update({
        "price_mode": PRICE_MODE_RANDOM,
        # 保留原固定价格，切回固定模式时无需丢失用户之前填写的值。
        "price": float(compat_price),
        "price_min": float(price_min),
        "price_max": float(price_max),
    })
    return normalized


def resolve_material_publish_price(item_data: dict) -> dict:
    """生成素材本次发布载荷中的实际价格。

    固定价格直接返回副本；无规格随机价格使用素材级区间；多规格随机价格使用
    每个 SKU 自己的区间独立取值，顶层价格取本次所有 SKU 随机结果的最低值。
    历史多规格素材缺少 SKU 区间时，兼容回退到素材级区间。
    """
    resolved = deepcopy(item_data)
    price_mode = str(item_data.get("price_mode") or PRICE_MODE_FIXED).strip().lower()
    if price_mode == PRICE_MODE_FIXED:
        return resolved
    if price_mode != PRICE_MODE_RANDOM:
        raise MaterialPriceError("价格模式无效，请检查素材配置")

    price_min = _parse_price(item_data.get("price_min"), "随机价格最小值")
    price_max = _parse_price(item_data.get("price_max"), "随机价格最大值")
    if price_min > price_max:
        raise MaterialPriceError("随机价格最小值不能大于最大值")

    sku_rows = resolved.get("sku_rows") or []
    sku_price_ranges: list[tuple[int, int]] = []
    for index, sku_row in enumerate(sku_rows, 1):
        if not isinstance(sku_row, dict):
            raise MaterialPriceError(f"第 {index} 个规格价格配置不正确")
        raw_sku_min = sku_row.get("price_min")
        raw_sku_max = sku_row.get("price_max")
        sku_min = _parse_price(
            price_min if raw_sku_min is None else raw_sku_min,
            f"第 {index} 个规格随机价格最小值",
        )
        sku_max = _parse_price(
            price_max if raw_sku_max is None else raw_sku_max,
            f"第 {index} 个规格随机价格最大值",
        )
        if sku_min > sku_max:
            raise MaterialPriceError(f"第 {index} 个规格随机价格最小值不能大于最大值")
        sku_price_ranges.append((int(sku_min * 100), int(sku_max * 100)))

    resolved_sku_prices = [
        Decimal(cents) / 100 for cents in _assign_unique_random_cents(sku_price_ranges)
    ]
    for sku_row, sku_price in zip(sku_rows, resolved_sku_prices):
        sku_row["price"] = f"{sku_price:.2f}"

    if resolved_sku_prices:
        resolved["price"] = f"{min(resolved_sku_prices):.2f}"
    else:
        min_cents = int(price_min * 100)
        max_cents = int(price_max * 100)
        resolved_price = Decimal(min_cents + randbelow(max_cents - min_cents + 1)) / 100
        resolved["price"] = f"{resolved_price:.2f}"
    return resolved


def format_publish_price(value: Any) -> str:
    """把发布日志中的价格统一格式化为两位小数。"""
    return f"{_parse_price(value, '发布价格'):.2f}"


__all__ = [
    "MATERIAL_PRICE_MODE_DICTIONARY",
    "PRICE_MODE_FIXED",
    "PRICE_MODE_RANDOM",
    "MaterialPriceError",
    "ensure_unique_random_prices_available",
    "format_publish_price",
    "normalize_material_price_fields",
    "resolve_material_publish_price",
]
