"""
发货工具函数模块

功能:
1. 发货内容参数替换
2. 发货内容处理和验证
3. 通用工具函数
4. 备注信息处理和变量替换

说明:
    核心的变量替换/内容渲染函数（process_delivery_content_with_description、
    replace_order_context_variables、recursive_replace_params）已下沉到
    common.services.delivery_utils，供 backend-web 与 websocket 共用，此处直接复用，
    避免重复实现。本模块仅保留 websocket 服务专用的辅助函数。
"""
from __future__ import annotations

from typing import Any, Dict
from loguru import logger

# 复用公共实现（下沉到 common，避免重复维护）
from common.services.delivery_utils import (
    process_delivery_content_with_description,
    recursive_replace_params,
    replace_order_context_variables,
)

__all__ = [
    "process_delivery_content_with_description",
    "recursive_replace_params",
    "replace_order_context_variables",
    "replace_delivery_params",
    "validate_delivery_content",
    "extract_order_info",
    "format_delivery_message",
    "is_delivery_trigger_keyword",
]


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
