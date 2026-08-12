"""
公共闲鱼发布服务

功能：
1. 统一加载闲鱼发布器实现
2. 单品和批量发布统一使用卖家工作台接口
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
    """创建旧版共享发布器实例，兼容其他非商品发布调用方。"""
    publisher_class = get_xianyu_publisher_class()
    return publisher_class(static_root=static_root)


def get_xianyu_direct_publisher_class() -> type[Any]:
    """动态加载单品接口发布器，避免批量浏览器模块被接口流程引入。"""
    return load_backend_web_class(
        module_name="common.services._shared_xianyu_direct_publisher",
        relative_path="backend-web/app/services/xianyu_direct_publisher.py",
        class_name="XianyuDirectPublisher",
    )


async def publish_single_item(
    item_data: dict,
    cookie: str,
    static_root: str | Path | None = None,
    *,
    account_id: str = "",
    owner_id: int | None = None,
) -> dict:
    """使用闲鱼接口执行一次发布，不启动浏览器。"""
    publisher_class = get_xianyu_direct_publisher_class()
    publisher = publisher_class(static_root=static_root)
    return await publisher.publish_item(
        item_data=item_data,
        cookie=cookie,
        account_id=account_id,
        owner_id=owner_id,
    )
