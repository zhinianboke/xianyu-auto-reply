"""
返佣系统专用闲鱼发布服务

功能：
1. 创建返佣系统专用闲鱼发布器实例
2. 为返佣系统提供独立的单品发布入口
3. 保持原通用发布服务不受影响
"""
from __future__ import annotations

from pathlib import Path

from common.services.promotion_xianyu_publisher import PromotionXianyuPublisher


def create_promotion_xianyu_publisher(static_root: str | Path | None = None) -> PromotionXianyuPublisher:
    """创建返佣系统专用闲鱼发布器实例。"""
    return PromotionXianyuPublisher(static_root=static_root)


async def publish_single_item(
    item_data: dict,
    cookie: str,
    static_root: str | Path | None = None,
) -> dict:
    """使用返佣系统专用发布器执行一次单品发布。"""
    publisher = create_promotion_xianyu_publisher(static_root=static_root)
    return await publisher.publish_item(
        item_data=item_data,
        cookie_data={"cookie": cookie},
        reuse_browser=False,
        should_close=True,
    )
