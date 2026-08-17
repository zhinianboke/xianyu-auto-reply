"""
平台分类选择状态构造工具。

功能：
1. 根据分类推荐接口返回的候选分类和完整属性卡定位选中项。
2. 按单品发布界面的规则生成平台需要的 currentCardList 和 selectedList。
3. 调用方传入的分类字段不全时，从属性卡中回填分类 ID 和名称，不做完整性校验。
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


def _match_candidate_value(
    category: dict[str, Any],
    value: dict[str, Any],
) -> tuple[bool, bool]:
    """
    按单品发布界面的优先级判断分类候选是否匹配属性卡选项。

    调用方可能只传回其中一个标识（如只有分类名称），因此按
    channel_cat_id、tb_cat_id、cat_id、分类名称的顺序逐个比对，
    取第一个双方都有值的标识作为判断依据。

    注意 cat_id 只存在于分类卡自带 catId 的候选上：推荐接口会用
    categoryPredictResult 给选中候选补 cat_id，这类补出来的 ID 在分类卡里
    找不到对应字段，只传它无法定位分类，需要靠返回值第一项告知调用方。

    Args:
        category: 调用方选中的分类对象。
        value: 分类卡中的一个候选选项。
    Returns:
        (是否存在双方都有值的可比对标识, 该选项是否即调用方所选分类)。
    """
    transport = _transport_data(value)
    comparisons = (
        (
            _as_text(category.get("channel_cat_id")),
            _as_text(value.get("channelCatId")) or _as_text(transport.get("channelCateId")),
        ),
        (
            _as_text(category.get("tb_cat_id")),
            _as_text(value.get("tbCatId")) or _as_text(transport.get("tbCatId")),
        ),
        (
            _as_text(category.get("cat_id")),
            _as_text(value.get("catId")),
        ),
        (
            _as_text(category.get("cat_name")) or _as_text(category.get("channel_cat_name")),
            _as_text(value.get("catName"))
            or _as_text(value.get("channelCatName"))
            or _as_text(transport.get("valueName")),
        ),
    )
    for selected_value, candidate_value in comparisons:
        if selected_value and candidate_value:
            return True, selected_value == candidate_value
    return False, False


def build_category_selection(
    card_list: list[dict[str, Any]],
    category: dict[str, Any],
) -> dict[str, Any]:
    """
    构造选择分类后重新获取动态属性所需的平台参数。

    与单品发布界面一致，不要求调用方回传完整的分类字段：只要能用
    channel_cat_id、tb_cat_id、cat_id 或分类名称中任意一个定位到分类卡里的选项，
    缺失的 channel_cat_id、tb_cat_id 和分类名称都从上一次推荐返回的 card_list 中取回。
    其中 cat_id 只在分类卡候选自带 catId 时可用（推荐接口用 categoryPredictResult
    给选中候选补出的 cat_id 在分类卡里没有对应字段），只传它时会明确报错提示换用其他标识。

    Args:
        card_list: 第一次分类推荐接口原样返回的完整 card_list。
        category: 第一次分类推荐接口 candidates 中用户选择的对象，允许字段不全。
    Returns:
        包含 current_card_list、selected_list 和分类 ID 的请求参数。
    Raises:
        CategorySelectionError: 分类缺少任何可用标识、标识无法比对或无法在分类卡中匹配选项。
    """
    if not card_list:
        raise CategorySelectionError("card_list不能为空，请传入分类推荐接口返回的完整card_list")

    category_name = _as_text(category.get("cat_name")) or _as_text(
        category.get("channel_cat_name")
    )
    channel_cat_id = _as_text(category.get("channel_cat_id"))
    tb_cat_id = _as_text(category.get("tb_cat_id"))
    selected_cat_id = _as_text(category.get("cat_id"))
    if not category_name and not channel_cat_id and not tb_cat_id and not selected_cat_id:
        raise CategorySelectionError(
            "所选分类缺少标识，cat_name、cat_id、channel_cat_id、tb_cat_id 至少需要一个"
        )

    current_card_list = deepcopy(card_list)
    selected_label: dict[str, Any] | None = None
    category_card_found = False
    # 分类卡里是否出现过与调用方标识可比对的候选，用于区分“标识不可用”和“选错分类”
    comparable_found = False
    # 匹配成功后按分类卡里的真实值回填，避免依赖调用方传入的分类字段
    resolved_cat_id = selected_cat_id
    resolved_cat_name = category_name
    resolved_channel_cat_id = channel_cat_id

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
            comparable, matched = _match_candidate_value(category, value)
            if comparable:
                comparable_found = True
            # 平台只接受一个选中分类；标识不全时可能有多个候选同名，只认第一个命中项
            selected = matched and selected_label is None
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
                # 与单品发布界面一致：分类卡和调用方都没有 tbCatId 时传 null 而不是空串
                "tbCatId": _as_text(value.get("tbCatId"))
                or _as_text(transport.get("tbCatId"))
                or tb_cat_id
                or None,
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
                # 调用方未传的分类标识，从分类卡命中的选项里取回
                resolved_cat_id = _as_text(value.get("catId")) or selected_cat_id
                resolved_cat_name = value_category_name
                resolved_channel_cat_id = value_channel_id

            value["isClicked"] = "1" if selected else "0"
            value["isUserClick"] = "1" if selected else "0"
            value["isUserCancel"] = None
            value["transportData"] = next_transport

    if not category_card_found:
        raise CategorySelectionError("card_list中缺少分类卡，请重新调用分类推荐接口")
    if selected_label is None:
        if not comparable_found:
            # 例如只传了 categoryPredictResult 补出来的 cat_id，分类卡候选里没有该字段可比对
            raise CategorySelectionError(
                "所选分类的标识无法与card_list中的候选比对，"
                "请改用 channel_cat_id、tb_cat_id 或 cat_name"
                "（cat_id 仅在分类卡候选自带 catId 时可用）"
            )
        raise CategorySelectionError("所选分类不在card_list中，请使用同一次分类推荐返回的数据")

    return {
        "current_card_list": current_card_list,
        "selected_list": [selected_label],
        "cat_id": resolved_cat_id,
        "cat_name": resolved_cat_name,
        "channel_cat_id": resolved_channel_cat_id,
    }


__all__ = ["CategorySelectionError", "build_category_selection"]
