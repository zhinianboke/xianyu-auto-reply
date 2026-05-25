"""
发货工具函数模块

功能:
1. 发货内容参数替换
2. 发货内容处理和验证
3. 通用工具函数
4. 备注信息处理和变量替换
"""
from __future__ import annotations

import re
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
        order_context: 订单上下文信息，包含 order_id/item_id/item_title/buyer_name/buyer_id/seller_name
        
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


def replace_delivery_params(
    content: str,
    order_id: str,
    item_id: str,
    item_title: str,
    buyer_name: str,
    buyer_id: str,
    seller_name: str,
) -> str:
    """替换发货内容中的参数变量
    
    支持的变量:
    - {order_id}: 订单ID
    - {item_id}: 商品ID
    - {item_title}: 商品标题
    - {buyer_name}: 买家昵称
    - {buyer_id}: 买家ID
    - {seller_name}: 卖家昵称
    
    Args:
        content: 原始内容
        order_id: 订单ID
        item_id: 商品ID
        item_title: 商品标题
        buyer_name: 买家昵称
        buyer_id: 买家ID
        seller_name: 卖家昵称
        
    Returns:
        替换后的内容
    """
    try:
        # 替换所有支持的变量
        result = content
        result = result.replace("{order_id}", order_id or "")
        result = result.replace("{item_id}", item_id or "")
        result = result.replace("{item_title}", item_title or "")
        result = result.replace("{buyer_name}", buyer_name or "")
        result = result.replace("{buyer_id}", buyer_id or "")
        result = result.replace("{seller_name}", seller_name or "")
        
        return result
        
    except Exception as e:
        logger.error(f"替换发货参数失败: {e}")
        return content


def validate_delivery_content(content: str, delivery_type: str) -> bool:
    """验证发货内容是否有效
    
    Args:
        content: 发货内容
        delivery_type: 发货类型(text/image/api/batch)
        
    Returns:
        是否有效
    """
    if not content or not content.strip():
        logger.warning(f"发货内容为空,类型: {delivery_type}")
        return False
    
    # 根据类型进行特定验证
    if delivery_type == "image":
        # 图片类型需要包含图片URL或路径
        if not (content.startswith("http") or content.startswith("/") or content.startswith("static/")):
            logger.warning(f"图片发货内容格式无效: {content}")
            return False
    
    return True


def extract_order_info(message_data: Dict[str, Any]) -> Dict[str, str]:
    """从消息数据中提取订单信息
    
    Args:
        message_data: 消息数据字典
        
    Returns:
        订单信息字典
    """
    try:
        # 提取基本信息
        order_info = {
            "order_id": "",
            "item_id": "",
            "item_title": "",
            "buyer_name": "",
            "buyer_id": "",
        }
        
        # 从不同字段提取信息
        if "bizOrderId" in message_data:
            order_info["order_id"] = str(message_data["bizOrderId"])
        
        if "itemId" in message_data:
            order_info["item_id"] = str(message_data["itemId"])
        
        if "itemTitle" in message_data:
            order_info["item_title"] = str(message_data["itemTitle"])
        
        if "buyerNick" in message_data:
            order_info["buyer_name"] = str(message_data["buyerNick"])
        
        if "buyerId" in message_data:
            order_info["buyer_id"] = str(message_data["buyerId"])
        
        return order_info
        
    except Exception as e:
        logger.error(f"提取订单信息失败: {e}")
        return {
            "order_id": "",
            "item_id": "",
            "item_title": "",
            "buyer_name": "",
            "buyer_id": "",
        }


def format_delivery_message(delivery_type: str, content: str, success: bool = True) -> str:
    """格式化发货消息
    
    Args:
        delivery_type: 发货类型
        content: 发货内容
        success: 是否成功
        
    Returns:
        格式化后的消息
    """
    type_names = {
        "api": "API发货",
        "text": "文本发货",
        "image": "图片发货",
        "batch": "批量发货",
    }
    
    type_name = type_names.get(delivery_type, "发货")
    status = "成功" if success else "失败"
    
    # 截断过长的内容
    display_content = content[:50] + "..." if len(content) > 50 else content
    
    return f"{type_name}{status}: {display_content}"


def is_delivery_trigger_keyword(message: str, keywords: list[str]) -> bool:
    """检查消息是否包含发货触发关键词
    
    Args:
        message: 消息内容
        keywords: 关键词列表
        
    Returns:
        是否包含触发关键词
    """
    if not message or not keywords:
        return False
    
    message_lower = message.lower().strip()
    
    for keyword in keywords:
        if keyword and keyword.lower().strip() in message_lower:
            return True
    
    return False
