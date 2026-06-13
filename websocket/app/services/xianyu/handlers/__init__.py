"""
消息处理模块

将 xianyu_async.py 中的消息处理逻辑拆分为独立的 handler 模块：
- MessageRouter: 消息路由和分发
- RedeliveryHandler: 重发货触发处理
- OrderStatusHandler: 订单状态处理
"""

from app.services.xianyu.handlers.message_router import MessageRouter
from app.services.xianyu.handlers.redelivery_handler import RedeliveryHandler
from app.services.xianyu.handlers.order_status_handler import OrderStatusHandler

__all__ = ['MessageRouter', 'RedeliveryHandler', 'OrderStatusHandler']
