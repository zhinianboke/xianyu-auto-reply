"""
商品上新监控任务服务

功能：
1. 兼容 backend-web 原导入路径
2. 复用 common 公共上新监控任务服务实现
"""
from __future__ import annotations

from common.services.listing_monitor_service import ListingMonitorService, _task_to_dict

__all__ = ["ListingMonitorService", "_task_to_dict"]
