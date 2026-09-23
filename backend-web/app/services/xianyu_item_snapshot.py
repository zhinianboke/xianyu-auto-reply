"""
闲鱼卖家后台 editdetail 快照工具。

功能：
1. 把 editdetail 返回的字符串化字段（"true"/"800"）规范化成 edit 接口需要的布尔/整数；
2. 判断表单中的图片/宝贝所在地/发货设置是否与平台快照一致，一致则直接复用平台数据；
3. 供载荷构造器与编辑服务共用，避免全量覆盖式编辑丢失未改动的字段。
"""
from __future__ import annotations

from typing import Any

from app.services.xianyu_direct_payload import text as _text


def as_bool(value: Any) -> bool:
    """把平台或历史调用方返回的布尔值转成 Python 布尔。

    Args:
        value: 原始值，可能是布尔、数字或字符串（true/1/yes/on）。
    Returns:
        bool: 仅当值为真布尔 True 或字符串 "true"（忽略大小写）时返回 True。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return _text(value).strip().lower() in {"true", "1", "yes", "on"}


def as_int(value: Any, default: int = 0) -> int:
    """把平台返回的数值（可能是字符串）转成整数，异常时返回默认值。

    Args:
        value: 平台返回的原始值，可能是字符串、数值或 None。
        default: 无法解析时返回的默认值。
    Returns:
        int: 解析后的整数，解析失败返回 default。
    """
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_snapshot_image(entry: dict[str, Any]) -> dict[str, Any]:
    """把 editdetail 返回的图片条目规范化成编辑接口需要的结构。

    editdetail 里所有值都是字符串（如 "major":"true"、"widthSize":"800"），
    而抓包的 edit 请求用的是真布尔/整数，这里统一按 edit 请求的形状转换。

    Args:
        entry: editdetail 的 imageInfoDOList 单个条目。
    Returns:
        dict: 与抓包 edit 请求一致的图片条目。
    """
    url = _text(entry.get("url"))
    extra_info = entry.get("extraInfo") if isinstance(entry.get("extraInfo"), dict) else {}
    return {
        "extraInfo": {
            "isH": "true" if as_bool(extra_info.get("isH")) else "false",
            "isT": "true" if as_bool(extra_info.get("isT")) else "false",
            "raw": "true" if as_bool(extra_info.get("raw")) else "false",
        },
        "heightSize": as_int(entry.get("heightSize"), 800),
        "isQrCode": as_bool(entry.get("isQrCode")),
        "labels": entry.get("labels") if isinstance(entry.get("labels"), list) else [],
        "major": as_bool(entry.get("major")),
        "templateIndex": _text(entry.get("templateIndex")) or "0",
        "thumbnail": _text(entry.get("thumbnail")) or url,
        "type": as_int(entry.get("type")),
        "url": url,
        "widthSize": as_int(entry.get("widthSize"), 800),
        "status": "done",
    }


def normalize_snapshot_post_fee(post_fee: dict[str, Any]) -> dict[str, Any]:
    """把 editdetail 的 itemPostFeeDTO 规范化成编辑接口需要的结构。

    Args:
        post_fee: editdetail 返回的 itemPostFeeDTO（值均为字符串）。
    Returns:
        dict: 与抓包 edit 请求一致的运费结构（6 个字段）。
    """
    return {
        "canFreeShipping": as_bool(post_fee.get("canFreeShipping")),
        "supportFreight": as_bool(post_fee.get("supportFreight")),
        "onlyTakeSelf": as_bool(post_fee.get("onlyTakeSelf")),
        "postPriceInCent": str(as_int(post_fee.get("postPriceInCent"))),
        "templateId": _text(post_fee.get("templateId")) or "0",
        "idleTemplateId": _text(post_fee.get("idleTemplateId")) or "0",
    }


def shipping_method_from_post_fee(post_fee: Any) -> str:
    """把平台 itemPostFeeDTO 反推成前端表单的发货方式取值。

    Args:
        post_fee: 平台返回的 itemPostFeeDTO。
    Returns:
        str: free / none / template / fixed 之一，无法识别时按 free 处理。
    """
    if not isinstance(post_fee, dict):
        return "free"
    # 「无需邮寄」与「支持自提」是两个独立开关：前者由运费能力组合决定，
    # 后者只由 onlyTakeSelf 决定，不能用自提开关反推发货方式。
    if not as_bool(post_fee.get("canFreeShipping")) and not as_bool(
        post_fee.get("supportFreight")
    ):
        return "none"
    template_id = _text(post_fee.get("templateId")) or _text(post_fee.get("idleTemplateId"))
    if template_id and template_id != "0":
        return "template"
    if as_int(post_fee.get("postPriceInCent")) > 0:
        return "fixed"
    return "free"


def snapshot_post_fee_unchanged(item_data: dict[str, Any], snapshot_post_fee: Any) -> bool:
    """判断表单中的发货设置与平台快照是否一致（一致则可原样复用快照）。

    Args:
        item_data: 前端表单数据，读取 shipping_method 与 postage。
        snapshot_post_fee: editdetail 返回的 itemPostFeeDTO。
    Returns:
        bool: 发货方式与运费金额都未改动时返回 True。
    """
    if not snapshot_post_fee_shipping_unchanged(item_data, snapshot_post_fee):
        return False
    # 自提开关是独立字段，调用方已传入时也必须参与一致性判断。
    if "support_pickup" in item_data:
        return as_bool(item_data.get("support_pickup")) == as_bool(
            snapshot_post_fee.get("onlyTakeSelf")
        )
    return True


def snapshot_post_fee_shipping_unchanged(
    item_data: dict[str, Any], snapshot_post_fee: Any
) -> bool:
    """判断发货方式与运费金额是否未变，不比较支持自提开关。

    编辑只切换「支持自提」时可据此保留平台原始模板/计费字段，避免用占位
    模板 ID 重建运费配置。

    Args:
        item_data: 前端表单数据，读取 shipping_method 与 postage。
        snapshot_post_fee: editdetail 返回的 itemPostFeeDTO。
    Returns:
        bool: 发货方式与运费金额一致时返回 True。
    """
    if not isinstance(snapshot_post_fee, dict):
        return False
    if (_text(item_data.get("shipping_method")) or "free") != shipping_method_from_post_fee(
        snapshot_post_fee
    ):
        return False
    try:
        form_postage = int(round(float(item_data.get("postage") or 0) * 100))
    except (TypeError, ValueError):
        form_postage = 0
    return as_int(snapshot_post_fee.get("postPriceInCent")) == form_postage


def snapshot_address_if_unchanged(
    item_data: dict[str, Any], snapshot: dict[str, Any] | None
) -> dict[str, str] | None:
    """宝贝所在地未改动时返回可直接提交的平台地址结构，否则返回 None。

    Args:
        item_data: 前端表单数据，读取 address。
        snapshot: editdetail 原始详情，发布场景为 None。
    Returns:
        dict | None: 地址未改动时返回平台地址结构（含 divisionId/gps/poiId），
            改动或无快照时返回 None，由调用方重新请求高德解析。
    """
    if not snapshot:
        return None
    snapshot_addr = snapshot.get("itemAddrDTO")
    if not isinstance(snapshot_addr, dict) or not _text(snapshot_addr.get("poiName")):
        return None
    if _text(item_data.get("address")) != _text(snapshot_addr.get("poiName")):
        return None
    return {
        key: _text(snapshot_addr.get(key))
        for key in ("area", "city", "divisionId", "gps", "poiId", "poiName", "prov")
    }


def snapshot_image_index(snapshot: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """按图片 URL 建立平台快照索引，供编辑时复用未改动的图片。

    Args:
        snapshot: editdetail 原始详情，发布场景为 None。
    Returns:
        dict: {图片URL: 规范化后的图片条目}，无快照时为空字典（图片全部重新上传）。
    """
    index: dict[str, dict[str, Any]] = {}
    if not snapshot:
        return index
    for entry in snapshot.get("imageInfoDOList") or []:
        if isinstance(entry, dict) and _text(entry.get("url")):
            index[_text(entry.get("url"))] = normalize_snapshot_image(entry)
    return index


def normalize_snapshot_video(entry: dict[str, Any]) -> dict[str, Any]:
    """把 editdetail 的视频条目规范化成编辑接口需要的结构。

    视频条目不能走 normalize_snapshot_image：那个函数返回固定的图片字段集，
    会把 videoUrl / mediaCloudFileId / videoMD5 / videoObject 这些视频必需字段
    （见 common/services/xianyu_publish_video.py 的 _video_payload）全部丢掉，
    而 edit 是全量覆盖提交，字段一丢平台上的视频就没了。
    因此这里保留平台返回的所有原始字段，只把字符串值转成提交接口用的原生类型。

    Args:
        entry: editdetail 的 imageInfoDOList 中 type 非 0 的条目。
    Returns:
        dict: 保留全部原始字段的视频条目。
    """
    normalized = dict(entry)
    extra_info = entry.get("extraInfo") if isinstance(entry.get("extraInfo"), dict) else {}
    normalized["extraInfo"] = {
        "isH": "true" if as_bool(extra_info.get("isH")) else "false",
        "isT": "true" if as_bool(extra_info.get("isT")) else "false",
        "raw": "true" if as_bool(extra_info.get("raw")) else "false",
    }
    # editdetail 的字段值全部是字符串，提交接口按抓包用的是原生类型
    normalized["type"] = as_int(entry.get("type"))
    normalized["major"] = as_bool(entry.get("major"))
    normalized["heightSize"] = as_int(entry.get("heightSize"))
    normalized["widthSize"] = as_int(entry.get("widthSize"))
    return normalized


def snapshot_video_items(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    """取出平台快照里的视频条目（type 非 0），编辑时原样回传避免丢失视频。

    Args:
        snapshot: editdetail 原始详情，发布场景为 None。
    Returns:
        list: 规范化后的视频条目列表，无快照时为空列表。
    """
    if not snapshot:
        return []
    items: list[dict[str, Any]] = []
    for entry in snapshot.get("imageInfoDOList") or []:
        if not isinstance(entry, dict):
            continue
        if as_int(entry.get("type")) != 0:
            items.append(normalize_snapshot_video(entry))
    return items


def snapshot_video_index(snapshot: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """按 mediaCloudFileId 建立平台视频索引，供编辑时复用未改动的视频。

    编辑弹窗回填平台视频时携带 file_id（= mediaCloudFileId）。提交时后端重新拉取快照，
    凭 file_id 命中此索引即可原样回传平台视频，既不丢视频也不对已在平台的视频重复上传。

    Args:
        snapshot: editdetail 原始详情，发布场景为 None。
    Returns:
        dict: {mediaCloudFileId: 规范化后的视频条目}，无快照时为空字典。
    """
    index: dict[str, dict[str, Any]] = {}
    for entry in snapshot_video_items(snapshot):
        file_id = _text(entry.get("mediaCloudFileId"))
        if file_id:
            index[file_id] = entry
    return index


def snapshot_user_rights(snapshot: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    """取出平台快照里的服务承诺开关（极速发货/不符退款等），编辑时原样回传。

    编辑是全量覆盖提交，若按发布默认值提交三项全 false，卖家原先开启的
    服务承诺会被静默关掉，因此有快照时必须复用平台原值。

    Args:
        snapshot: editdetail 原始详情，发布场景为 None。
    Returns:
        list | None: 规范化后的服务承诺列表（enable 转为布尔），
            无快照或快照未返回该字段时返回 None，由调用方使用发布默认值。
    """
    if not snapshot:
        return None
    protocols = snapshot.get("userRightsProtocols")
    if not isinstance(protocols, list) or not protocols:
        return None
    items: list[dict[str, Any]] = []
    for entry in protocols:
        if not isinstance(entry, dict):
            continue
        service_code = _text(entry.get("serviceCode"))
        if not service_code:
            continue
        items.append({"enable": as_bool(entry.get("enable")), "serviceCode": service_code})
    return items or None


__all__ = [
    "as_bool",
    "as_int",
    "normalize_snapshot_image",
    "normalize_snapshot_post_fee",
    "normalize_snapshot_video",
    "shipping_method_from_post_fee",
    "snapshot_address_if_unchanged",
    "snapshot_image_index",
    "snapshot_post_fee_unchanged",
    "snapshot_post_fee_shipping_unchanged",
    "snapshot_user_rights",
    "snapshot_video_index",
    "snapshot_video_items",
]
