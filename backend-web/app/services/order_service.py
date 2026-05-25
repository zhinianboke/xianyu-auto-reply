"""
订单服务

功能：
1. 订单列表查询（支持按账号、状态筛选）
2. 订单详情查询
3. 订单状态更新
4. 待发货订单查询
5. 关联商品表获取商品标题

此文件从common.services.order_service导入，保持向后兼容
"""
from common.services.order_service import OrderService

__all__ = ["OrderService"]
