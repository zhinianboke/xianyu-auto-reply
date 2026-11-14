"""闲鱼接口发布的规格载荷与响应解析辅助函数。"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse


class DirectPublishError(RuntimeError):
    """直连接口发布前置校验或载荷构建异常。"""

    def __init__(self, message: str, *, account_invalid: bool = False) -> None:
        super().__init__(message)
        self.account_invalid = account_invalid


def text(value: Any) -> str:
    """安全转换接口输入为去除空白的文本。"""
    return str(value).strip() if value is not None else ""


def build_item_text_dto(title: str, description: str) -> dict[str, Any]:
    """构造标题与正文分离的闲鱼商品文本载荷。

    Args:
        title: 商品标题。
        description: 商品正文描述。
    Returns:
        dict: 可直接写入发布载荷 ``itemTextDTO`` 的文本配置。
    """
    return {
        "desc": description,
        "title": title,
        # 开启后平台分别读取 title 与 desc，避免将正文第一行当作商品标题。
        "titleDescSeparate": True,
    }


def price_in_cent(value: Any, field_name: str) -> str:
    """将元价格转换为字符串分值。"""
    try:
        cents = round(float(value) * 100)
    except (TypeError, ValueError) as exc:
        raise DirectPublishError(f"{field_name}格式不正确") from exc
    if cents <= 0:
        raise DirectPublishError(f"{field_name}必须大于0")
    return str(cents)


def build_sku_payload(
    item_data: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]], bool]:
    """构造 itemProperties、itemSkuList 和待上传的规格图片来源。"""
    raw_specs = item_data.get("specifications") or []
    raw_rows = item_data.get("sku_rows") or []
    if not raw_specs and not raw_rows:
        return [], [], [], False
    if not raw_specs:
        raise DirectPublishError("商品包含 SKU，但未提供规格定义")
    if not raw_rows:
        raise DirectPublishError("请选择规格组合并填写每个 SKU 的价格和库存")

    item_properties: list[dict[str, Any]] = []
    property_image_sources: list[dict[str, str]] = []
    spec_names: list[str] = []
    allowed_values: dict[str, set[str]] = {}
    expected_count = 1
    for index, specification in enumerate(raw_specs, 1):
        if not isinstance(specification, dict):
            raise DirectPublishError(f"第 {index} 个规格格式不正确")
        name = text(specification.get("name"))
        if not name:
            raise DirectPublishError(f"第 {index} 个规格名称不能为空")
        if name in allowed_values:
            raise DirectPublishError(f"规格名称重复：{name}")
        raw_values = specification.get("values") or []
        values: list[str] = []
        for value in raw_values:
            value_name = text(value.get("name") if isinstance(value, dict) else value)
            if not value_name:
                continue
            if value_name in values:
                raise DirectPublishError(f"规格“{name}”存在重复规格值：{value_name}")
            values.append(value_name)
        if not values:
            raise DirectPublishError(f"规格“{name}”至少需要一个规格值")
        spec_names.append(name)
        allowed_values[name] = set(values)
        expected_count *= len(values)
        property_values: list[dict[str, Any]] = []
        has_value_image = False
        for value in raw_values:
            value_name = text(value.get("name") if isinstance(value, dict) else value)
            if not value_name or value_name not in values:
                continue
            property_values.append({"propertyValue": value_name})
            image_source = text(value.get("image")) if isinstance(value, dict) else ""
            if image_source:
                has_value_image = True
                property_image_sources.append(
                    {"property_name": name, "property_value": value_name, "source": image_source}
                )
        item_properties.append(
            {
                "propertyName": name,
                "supportImage": bool(specification.get("support_image")) or has_value_image,
                "propertyValues": property_values,
            }
        )

    # 抓包确认：闲鱼同一商品只允许一组规格带规格图（另一组 supportImage 为 false），
    # 两组都带图会被平台拒绝，此处提前给出中文错误而不是把不合法载荷发出去
    image_group_names = sorted({source["property_name"] for source in property_image_sources})
    if len(image_group_names) > 1:
        raise DirectPublishError(
            f"闲鱼只允许一组规格带规格图，当前有 {len(image_group_names)} 组带图："
            f"{'、'.join(image_group_names)}，请只保留一组"
        )
    # 只勾选了「支持添加图片」但一张都没传时同样不能有两组 supportImage=true：
    # 带图的那组优先，都没带图时保留第一个被勾选的组，其余置 false。
    if sum(1 for prop in item_properties if prop["supportImage"]) > 1:
        keep = image_group_names[0] if image_group_names else next(
            prop["propertyName"] for prop in item_properties if prop["supportImage"]
        )
        for prop in item_properties:
            prop["supportImage"] = prop["propertyName"] == keep

    if len(raw_rows) != expected_count:
        raise DirectPublishError(
            f"规格组合数量不完整：应有 {expected_count} 组，实际收到 {len(raw_rows)} 组"
        )
    return (
        item_properties,
        _build_sku_rows(raw_rows, spec_names, allowed_values),
        property_image_sources,
        True,
    )


def _build_sku_rows(
    raw_rows: list[Any], spec_names: list[str], allowed_values: dict[str, set[str]]
) -> list[dict[str, Any]]:
    """校验规格组合并生成接口 itemSkuList。"""
    item_sku_list: list[dict[str, Any]] = []
    seen_combinations: set[tuple[str, ...]] = set()
    for index, row in enumerate(raw_rows, 1):
        if not isinstance(row, dict):
            raise DirectPublishError(f"第 {index} 个 SKU 格式不正确")
        row_specs = row.get("specs") or {}
        if not isinstance(row_specs, dict):
            raise DirectPublishError(f"第 {index} 个 SKU 的规格值格式不正确")
        property_list: list[dict[str, str]] = []
        combination: list[str] = []
        for spec_name in spec_names:
            value_name = text(row_specs.get(spec_name))
            if not value_name:
                raise DirectPublishError(f"第 {index} 个 SKU 缺少规格“{spec_name}”")
            if value_name not in allowed_values[spec_name]:
                raise DirectPublishError(f"第 {index} 个 SKU 的规格值无效：{spec_name}={value_name}")
            combination.append(value_name)
            property_list.append({"propertyText": spec_name, "valueText": value_name})
        combination_key = tuple(combination)
        if combination_key in seen_combinations:
            raise DirectPublishError(f"第 {index} 个 SKU 与已有规格组合重复")
        seen_combinations.add(combination_key)
        try:
            stock = int(row.get("stock", 0))
        except (TypeError, ValueError) as exc:
            raise DirectPublishError(f"第 {index} 个 SKU 库存格式不正确") from exc
        if stock < 0 or stock > 999999:
            raise DirectPublishError(f"第 {index} 个 SKU 库存必须在 0 到 999999 之间")
        item_sku_list.append(
            {
                "priceInCent": price_in_cent(row.get("price"), f"第 {index} 个 SKU 售价"),
                "quantity": stock,
                "propertyList": property_list,
            }
        )
    return item_sku_list


def extract_item_id_from_url(value: str) -> str | None:
    """从商品查询参数或旧版路径地址中提取商品 ID。"""
    if not value:
        return None
    try:
        query = parse_qs(urlparse(value).query or "")
        for key in ("id", "item_id", "itemId"):
            candidate = query.get(key)
            if candidate and candidate[0]:
                return text(candidate[0])
    except Exception:
        pass
    match = re.search(r"/item/(\d+)", value)
    return match.group(1) if match else None


def find_item_reference(value: Any) -> tuple[str | None, str | None]:
    """递归提取发布响应中的商品 ID 和商品链接。"""
    item_id: str | None = None
    item_url: str | None = None
    if isinstance(value, dict):
        for key, current in value.items():
            normalized = key.lower()
            if normalized in {"itemid", "item_id", "idleitemid"} and current is not None:
                item_id = text(current) or item_id
            elif normalized in {"itemurl", "item_url", "url"} and isinstance(current, str):
                extracted_id = extract_item_id_from_url(current)
                item_id = item_id or extracted_id
                if "goofish.com" in current and (extracted_id or "/item" in current):
                    item_url = current
            nested_id, nested_url = find_item_reference(current)
            item_id = item_id or nested_id
            item_url = item_url or nested_url
    elif isinstance(value, list):
        for current in value:
            nested_id, nested_url = find_item_reference(current)
            item_id = item_id or nested_id
            item_url = item_url or nested_url
    return item_id, item_url
