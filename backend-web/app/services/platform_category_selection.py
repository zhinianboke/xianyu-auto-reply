"""
平台分类选择状态构造工具。

功能：
1. 根据分类推荐接口返回的候选分类和完整属性卡定位选中项。
2. 按单品发布界面的规则生成平台需要的 currentCardList 和 selectedList。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


class CategorySelectionError(RuntimeError):
    """分类选择数据不完整或无法匹配属性卡时抛出的业务异常。"""


def _as_text(value: Any) -> str:
    """将分类字段安全转换为去除首尾空格的字符串。"""
    return str(value).strip() if value is not None else ""


def _transport_data(value: dict[str, Any]) -> dict[str, Any]:
    """获取属性值中的 transportData 字典。"""
    transport = value.get("transportData")
    return transport if isinstance(transport, dict) else {}


def _candidate_matches_value(
    category: dict[str, Any],
    value: dict[str, Any],
) -> bool:
    """按单品发布界面的优先级判断分类候选是否匹配属性卡选项。"""
    transport = _transport_data(value)
    channel_cat_id = _as_text(value.get("channelCatId")) or _as_text(
        transport.get("channelCateId")
    )
    tb_cat_id = _as_text(value.get("tbCatId")) or _as_text(transport.get("tbCatId"))
    cat_name = _as_text(value.get("catName")) or _as_text(transport.get("valueName"))

    selected_channel_cat_id = _as_text(category.get("channel_cat_id"))
    selected_tb_cat_id = _as_text(category.get("tb_cat_id"))
    selected_cat_id = _as_text(category.get("cat_id"))
    selected_cat_name = _as_text(category.get("cat_name"))

    if selected_channel_cat_id and channel_cat_id:
        return selected_channel_cat_id == channel_cat_id
    if selected_tb_cat_id and tb_cat_id:
        return selected_tb_cat_id == tb_cat_id
    if selected_channel_cat_id or selected_tb_cat_id:
        return False
    if selected_cat_id and _as_text(value.get("catId")):
        return selected_cat_id == _as_text(value.get("catId"))
    return bool(selected_cat_name and selected_cat_name == cat_name)


def build_category_selection(
    card_list: list[dict[str, Any]],
    category: dict[str, Any],
) -> dict[str, Any]:
    """
    构造选择分类后重新获取动态属性所需的平台参数。

    Args:
        card_list: 第一次分类推荐接口原样返回的完整 card_list。
        category: 第一次分类推荐接口 candidates 中用户选择的完整对象。
    Returns:
        包含 current_card_list、selected_list 和分类 ID 的请求参数。
    Raises:
        CategorySelectionError: 分类字段不完整或无法在分类卡中匹配选项。
    """
    if not card_list:
        raise CategorySelectionError("card_list不能为空，请传入分类推荐接口返回的完整card_list")

    category_name = _as_text(category.get("cat_name")) or _as_text(
        category.get("channel_cat_name")
    )
    channel_cat_id = _as_text(category.get("channel_cat_id"))
    tb_cat_id = _as_text(category.get("tb_cat_id"))
    if not category_name or not channel_cat_id or not tb_cat_id:
        raise CategorySelectionError(
            "所选分类信息不完整，必须包含分类名称、channel_cat_id和tb_cat_id"
        )

    current_card_list = deepcopy(card_list)
    selected_label: dict[str, Any] | None = None
    category_card_found = False

    for card in current_card_list:
        if not isinstance(card, dict) or _as_text(card.get("propertyId")) != "-10000":
            continue
        category_card_found = True
        values = card.get("valuesList")
        if not isinstance(values, list):
            continue

        for value in values:
            if not isinstance(value, dict):
                continue
            selected = _candidate_matches_value(category, value)
            transport = _transport_data(value)
            value_channel_id = (
                _as_text(value.get("channelCatId"))
                or _as_text(transport.get("channelCateId"))
                or channel_cat_id
            )
            value_category_name = (
                _as_text(value.get("catName"))
                or _as_text(value.get("channelCatName"))
                or category_name
            )
            properties = (
                f"-10000##分类:{value_channel_id}##{value_category_name}"
                if value_channel_id
                else _as_text(value.get("properties"))
            )
            next_transport = {
                **transport,
                "channelCateName": _as_text(value.get("channelCatName"))
                or _as_text(transport.get("channelCateName"))
                or _as_text(category.get("channel_cat_name"))
                or category_name,
                "valueId": None,
                "channelCateId": value_channel_id,
                "valueName": None,
                "tbCatId": _as_text(value.get("tbCatId"))
                or _as_text(transport.get("tbCatId"))
                or tb_cat_id,
                "subPropertyId": None,
                "labelType": _as_text(transport.get("labelType")) or "common",
                "subValueId": None,
                "labelId": None,
                "propertyName": "分类",
                "isUserClick": "1" if selected else "0",
                "isUserCancel": None,
                "from": "newPublishChoice",
                "propertyId": "-10000",
                "labelFrom": "newPublish",
                "properties": properties,
            }
            if selected:
                next_transport["text"] = value_category_name
                selected_label = next_transport

            value["isClicked"] = "1" if selected else "0"
            value["isUserClick"] = "1" if selected else "0"
            value["isUserCancel"] = None
            value["transportData"] = next_transport

    if not category_card_found:
        raise CategorySelectionError("card_list中缺少分类卡，请重新调用分类推荐接口")
    if selected_label is None:
        raise CategorySelectionError("所选分类不在card_list中，请使用同一次分类推荐返回的数据")

    return {
        "current_card_list": current_card_list,
        "selected_list": [selected_label],
        "cat_id": _as_text(category.get("cat_id")),
        "cat_name": category_name,
        "channel_cat_id": channel_cat_id,
    }


__all__ = ["CategorySelectionError", "build_category_selection"]
