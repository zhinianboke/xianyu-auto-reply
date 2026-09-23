"""
公共闲鱼发布服务

功能：
1. 统一加载闲鱼发布器实现
2. 保留鱼小铺卖家工作台发布逻辑
3. 提供普通卖家能力检测与独立发布入口
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


def get_xianyu_personal_publisher_class() -> type[Any]:
    """动态加载普通卖家单品发布器。"""
    return load_backend_web_class(
        module_name="common.services._shared_xianyu_personal_publisher",
        relative_path="backend-web/app/services/xianyu_personal_publisher.py",
        class_name="XianyuPersonalPublisher",
    )


def get_publish_account_capability_service_class() -> type[Any]:
    """动态加载发布账号能力检测服务。"""
    return load_backend_web_class(
        module_name="common.services._shared_publish_account_capability_service",
        relative_path="backend-web/app/services/publish_account_capability_service.py",
        class_name="PublishAccountCapabilityService",
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


async def detect_publish_account_capability(
    cookie: str,
    *,
    account_id: str,
    owner_id: int | None = None,
) -> dict:
    """查询账号是否开通鱼小铺及其发布能力。"""
    service_class = get_publish_account_capability_service_class()
    service = service_class()
    return await service.detect(account_id=account_id, cookie=cookie, owner_id=owner_id)


def ensure_publish_capability_reliable(capability: dict) -> dict:
    """发布链路加严：把不可信的「个人卖家」判定转成明确失败。

    鱼小铺卖家后台的发布初始化接口失败时（闲鱼限流、系统异常、风控、网络超时，
    或返回了无法识别的配置），检测会回落到个人版发布页判定，而个人版对鱼小铺账号
    可能返回个人卖家的服务费文案，从而把鱼小铺账号误判成普通卖家。发布一旦按个人版
    接口落地，多规格、独立库存等能力会丢失，且商品已经上架无法回滚，因此发布链路
    （单品发布、批量发布、公开接口发布）宁可报错不发布。
    编辑与商品同步不调用本函数：它们只在判定为鱼小铺时才继续，误判只会拒绝操作，
    不会把商品按个人版写到平台。

    Args:
        capability: detect_publish_account_capability 的返回。
    Returns:
        dict: 判定可信时原样返回；不可信时返回同结构的 success=False 结果。
    """
    if not capability.get("success") or capability.get("is_fish_shop"):
        return capability
    if capability.get("detection_reliable", True):
        return capability
    # 带上具体原因（限流码/网络异常/无法识别的配置），便于用户与运维区分成因
    reason = str(capability.get("detection_unreliable_reason") or "鱼小铺后台发布配置暂时取不到")
    return {
        **capability,
        "success": False,
        "message": (
            f"账号发布能力检测不可信：{reason}，无法确认账号是否开通鱼小铺。"
            "为避免鱼小铺账号被按个人卖家发布，本次未发布，请稍后重试"
        ),
    }


async def publish_personal_single_item(
    item_data: dict,
    cookie: str,
    static_root: str | Path | None = None,
    *,
    account_id: str = "",
    owner_id: int | None = None,
) -> dict:
    """使用普通卖家网页接口执行一次发布。"""
    publisher_class = get_xianyu_personal_publisher_class()
    publisher = publisher_class(static_root=static_root)
    return await publisher.publish_item(
        item_data=item_data,
        cookie=cookie,
        account_id=account_id,
        owner_id=owner_id,
    )
