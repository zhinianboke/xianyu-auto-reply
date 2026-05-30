"""
发货工具函数模块（公共版）

功能:
1. 发货内容参数替换
2. 发货内容处理和变量替换
3. 递归参数替换

说明:
    本模块从 websocket/app/services/xianyu/delivery_utils.py 下沉而来，
    供 backend-web（提货接口）、websocket（自动发货）共用，避免重复实现。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from loguru import logger


def process_delivery_content_with_description(
    delivery_content: str,
    card_description: str,
    order_context: Optional[Dict[str, str]] = None,
) -> str:
    """处理发货内容和备注信息，实现变量替换

    支持的变量:
    - {DELIVERY_CONTENT}: 发货内容
    - {order_id}: 订单ID
    - {item_id}: 商品ID
    - {item_title}: 商品标题
    - {buyer_name}: 买家昵称
    - {buyer_id}: 买家ID
    - {seller_name}: 卖家昵称

    Args:
        delivery_content: 发货内容
        card_description: 卡券备注信息
        order_context: 订单上下文信息

    Returns:
        处理后的发货内容
    """
    try:
        # 如果没有备注信息，直接返回发货内容
        if not card_description or not card_description.strip():
            return delivery_content

        # 替换备注中的 {DELIVERY_CONTENT} 变量
        processed_description = card_description.replace('{DELIVERY_CONTENT}', delivery_content)

        # 替换订单上下文变量
        if order_context:
            for key, value in order_context.items():
                placeholder = f"{{{key}}}"
                if placeholder in processed_description:
                    processed_description = processed_description.replace(placeholder, str(value) if value else "")

        # 如果备注中包含任何已知变量，返回处理后的备注
        has_any_variable = '{DELIVERY_CONTENT}' in card_description
        if order_context:
            for key in order_context:
                if f"{{{key}}}" in card_description:
                    has_any_variable = True
                    break

        if has_any_variable:
            return processed_description
        else:
            # 如果备注中没有变量，将备注和发货内容组合
            return f"{processed_description}\n\n{delivery_content}"

    except Exception as e:
        logger.error(f"处理备注信息失败: {e}")
        # 出错时返回原始发货内容
        return delivery_content


def replace_order_context_variables(text: str, order_context: Optional[Dict[str, str]] = None) -> str:
    """仅替换文本中的订单上下文变量（不处理 DELIVERY_CONTENT）

    用于图片类型卡券备注等场景，备注中没有 DELIVERY_CONTENT 但可能有订单变量。

    Args:
        text: 原始文本
        order_context: 订单上下文信息

    Returns:
        替换后的文本
    """
    if not text or not order_context:
        return text or ""
    try:
        result = text
        for key, value in order_context.items():
            placeholder = f"{{{key}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value) if value else "")
        return result
    except Exception as e:
        logger.error(f"替换订单上下文变量失败: {e}")
        return text


def recursive_replace_params(obj: Any, param_mapping: dict) -> Any:
    """递归替换参数中的占位符

    Args:
        obj: 要处理的对象（dict/list/str/其他）
        param_mapping: 参数映射字典

    Returns:
        替换后的对象
    """
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            result[key] = recursive_replace_params(value, param_mapping)
        return result
    elif isinstance(obj, list):
        return [recursive_replace_params(item, param_mapping) for item in obj]
    elif isinstance(obj, str):
        # 替换字符串中的占位符
        result = obj
        for param_key, param_value in param_mapping.items():
            placeholder = f"{{{param_key}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(param_value))
        return result
    else:
        return obj
