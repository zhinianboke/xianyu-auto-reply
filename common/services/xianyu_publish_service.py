"""
公共闲鱼发布服务

功能：
1. 统一加载闲鱼发布器实现
2. 为不同后端提供共享的直调发布入口
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from common.services.backend_web_loader import load_backend_web_class


def get_xianyu_publisher_class() -> type[Any]:
    """动态加载并返回共享闲鱼发布器类。"""
    return load_backend_web_class(
        module_name="common.services._shared_xianyu_publisher",
        relative_path="backend-web/app/services/xianyu_publisher.py",
        class_name="XianyuPublisher",
    )


def create_xianyu_publisher(static_root: str | Path | None = None) -> Any:
    """创建一个共享闲鱼发布器实例。"""
    publisher_class = get_xianyu_publisher_class()
    return publisher_class(static_root=static_root)


async def publish_single_item(
    item_data: dict,
    cookie: str,
    static_root: str | Path | None = None,
) -> dict:
    """使用共享发布器执行一次单品发布。"""
    publisher = create_xianyu_publisher(static_root=static_root)
    return await publisher.publish_item(
        item_data=item_data,
        cookie_data={"cookie": cookie},
        reuse_browser=False,
        should_close=True,
    )
