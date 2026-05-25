"""
商品发布图片辅助服务

功能：
1. 兼容旧导入路径
2. 转发到 common 公共发布图片服务
"""
from __future__ import annotations

from common.services.publish_image_service import cleanup_temp_images, download_remote_image

__all__ = ["download_remote_image", "cleanup_temp_images"]
