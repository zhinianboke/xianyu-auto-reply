"""
远程官方内容服务

功能：
1. 从远程官方服务器拉取公开内容（广告、公告等，与桌面版仪表盘同源接口）
2. 对远程内容做来源标记与 ID 转换，避免与本地数据 ID 冲突
3. 网络异常时静默降级，仅返回空结果，不影响本地内容展示
"""
from __future__ import annotations

import asyncio
import logging
import ssl
from typing import Any

import aiohttp

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 远程公开接口路径（与本服务保持一致，官方服务器同样暴露这些接口）
_REMOTE_ADS_PATH = "/api/v1/advertisements/public"
_REMOTE_ANNOUNCEMENTS_PATH = "/api/v1/announcements/public"
_REMOTE_POPUP_ANNOUNCEMENTS_PATH = "/api/v1/popup-announcements/public"
# 远程请求超时（秒）：该接口在用户请求链路中同步等待，超时设小以降低对本地内容展示的阻塞
_REMOTE_TIMEOUT = 4
# 远程拉取使用的固定 User-Agent：用于识别「服务器之间的远程拉取请求」，
# 防止官方服务器在处理远程拉取时再次去拉自己，造成 HTTP 层递归自调用
REMOTE_USER_AGENT = "XianyuBackend-Remote/1.0"


def is_remote_fetch_request(user_agent: str | None) -> bool:
    """判断该请求是否来自服务器间的远程拉取（避免递归自调用）"""
    return bool(user_agent) and REMOTE_USER_AGENT in user_agent


async def _fetch_remote_json(path: str) -> dict[str, Any] | None:
    """
    从远程官方服务器以 GET 方式拉取 JSON 数据

    远程站点证书可能不被信任，跳过校验（与桌面版仪表盘行为一致）。
    任何网络/解析异常都静默降级，返回 None。

    Args:
        path: 远程接口路径（以 / 开头）

    Returns:
        解析后的 JSON 字典，失败时返回 None
    """
    settings = get_settings()
    base_url = (settings.remote_official_base_url or "").strip().rstrip("/")
    if not base_url:
        return None

    url = f"{base_url}{path}"

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    try:
        timeout = aiohttp.ClientTimeout(total=_REMOTE_TIMEOUT)
        headers = {"User-Agent": REMOTE_USER_AGENT}
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, ssl=ssl_ctx) as resp:
                if resp.status != 200:
                    logger.warning(f"远程接口 {path} 返回非 200 状态: {resp.status}")
                    return None
                return await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.warning(f"拉取远程接口 {path} 失败: {e}")
        return None
    except Exception as e:
        logger.warning(f"拉取远程接口 {path} 异常: {e}")
        return None


# ==================== 远程广告 ====================

def _to_absolute_remote_url(url: str | None, base_url: str) -> str | None:
    """
    将远程内容中的相对资源路径转换为远程官方服务器的绝对地址

    远程广告的 image_url 多为相对路径（如 /static/uploads/images/xxx.jpg），
    它相对的是远程服务器；若不转换，前端 <img src> 会按本地源解析导致图片 404。
    已是绝对地址（http/https）或为空时原样返回。

    Args:
        url: 原始 URL（可能是相对路径、绝对地址或 None）
        base_url: 远程官方服务器基址（不含末尾斜杠）

    Returns:
        绝对地址，或原值
    """
    if not url:
        return url
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/") and base_url:
        return f"{base_url}{url}"
    return url


def _normalize_remote_ad(ad: dict[str, Any], seq: int, base_url: str) -> dict[str, Any]:
    """规范化单条远程广告：标记来源为 remote、ID 取负避免与本地正数 ID 冲突，
    并将相对图片路径补全为远程官方服务器的绝对地址。"""
    item = dict(ad)
    item["source"] = "remote"
    item["id"] = -seq
    item["image_url"] = _to_absolute_remote_url(item.get("image_url"), base_url)
    return item


async def fetch_remote_public_ads(
    local_dedup_keys: set[tuple[str | None, str | None]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    拉取远程官方服务器的公开广告并规范化

    Args:
        local_dedup_keys: 本地广告去重键集合（标题, 链接），命中的远程广告将被跳过，
            避免官方服务器自身部署时重复展示自己的广告

    Returns:
        {"carousel": [...], "text": [...]}，失败或未启用时返回空分组
    """
    empty: dict[str, list[dict[str, Any]]] = {"carousel": [], "text": []}
    settings = get_settings()
    if not settings.enable_remote_ads:
        return empty

    base_url = (settings.remote_official_base_url or "").strip().rstrip("/")

    data = await _fetch_remote_json(_REMOTE_ADS_PATH)
    if not data or not data.get("success") or not data.get("data"):
        return empty

    remote = data["data"]
    raw_carousel = remote.get("carousel") or []
    raw_text = remote.get("text") or []

    dedup = local_dedup_keys or set()
    carousel: list[dict[str, Any]] = []
    text: list[dict[str, Any]] = []
    seq = 0

    for ad in raw_carousel:
        if (ad.get("title"), ad.get("link")) in dedup:
            continue
        seq += 1
        carousel.append(_normalize_remote_ad(ad, seq, base_url))

    for ad in raw_text:
        if (ad.get("title"), ad.get("link")) in dedup:
            continue
        seq += 1
        text.append(_normalize_remote_ad(ad, seq, base_url))

    return {"carousel": carousel, "text": text}


# ==================== 远程公告 ====================

def _normalize_remote_announcement(ann: dict[str, Any], seq: int) -> dict[str, Any]:
    """规范化单条远程公告：标记来源为 remote，并将 ID 取负避免与本地正数 ID 冲突"""
    item = dict(ann)
    item["source"] = "remote"
    item["id"] = -seq
    return item


async def fetch_remote_public_announcements(
    local_dedup_keys: set[tuple[str | None, str | None]] | None = None,
) -> list[dict[str, Any]]:
    """
    拉取远程官方服务器的公开公告并规范化

    Args:
        local_dedup_keys: 本地公告去重键集合（标题, 内容），命中的远程公告将被跳过，
            避免官方服务器自身部署时重复展示自己的公告

    Returns:
        公告列表，失败或未启用时返回空列表
    """
    if not get_settings().enable_remote_announcements:
        return []

    data = await _fetch_remote_json(_REMOTE_ANNOUNCEMENTS_PATH)
    if not data or not data.get("success") or not data.get("data"):
        return []

    raw_items = data["data"].get("items") or []
    dedup = local_dedup_keys or set()
    items: list[dict[str, Any]] = []
    seq = 0

    for ann in raw_items:
        if (ann.get("title"), ann.get("content")) in dedup:
            continue
        seq += 1
        items.append(_normalize_remote_announcement(ann, seq))

    return items


# ==================== 远程弹窗公告 ====================

async def fetch_remote_public_popup_announcements(
    local_dedup_keys: set[tuple[str | None, str | None]] | None = None,
) -> list[dict[str, Any]]:
    """
    拉取远程官方服务器的公开弹窗公告并规范化

    Args:
        local_dedup_keys: 本地弹窗公告去重键集合（标题, 内容），命中的远程弹窗公告将被跳过，
            避免官方服务器自身部署时重复展示自己的弹窗公告

    Returns:
        弹窗公告列表，失败或未启用时返回空列表
    """
    if not get_settings().enable_remote_popup_announcements:
        return []

    data = await _fetch_remote_json(_REMOTE_POPUP_ANNOUNCEMENTS_PATH)
    if not data or not data.get("success") or not data.get("data"):
        return []

    raw_items = data["data"].get("items") or []
    dedup = local_dedup_keys or set()
    items: list[dict[str, Any]] = []
    seq = 0

    for ann in raw_items:
        if (ann.get("title"), ann.get("content")) in dedup:
            continue
        seq += 1
        # 弹窗公告与公告结构一致（source=remote、ID 取负），复用公告的规范化逻辑
        items.append(_normalize_remote_announcement(ann, seq))

    return items
