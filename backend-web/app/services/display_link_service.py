"""展示入口（display_links）校验与合并服务。

商品级展示入口与用户级通用模板共用同一套条目契约：
- link:  {"name", "type": "link",  "url", "note"?}
- text:  {"name", "type": "text",  "title", "content"}
- image: {"name", "type": "image", "url", "note"?}

安全：规范化按白名单收敛字段，防止误拷的 headers/Cookie 等键随提货页下发泄漏给买家。
"""
from __future__ import annotations

from typing import Any

ENTRY_TYPES = ("link", "text", "image")
MAX_TEXT_CONTENT_LEN = 2000
# 与 xy_display_link_templates 列宽一致：超长写入会被数据库拒绝（500），故在入口处拦下
MAX_NAME_LEN = 255
MAX_URL_LEN = 512
MAX_NOTE_LEN = 255
MAX_TITLE_LEN = 255


def _has_dotdot_segment(url: str) -> bool:
    """URL 是否含 ``..`` 路径段（目录穿越）。

    按 ``/`` 切分后精确比对整段，查询串里的 ``..``（如 ``?k=a..b``）不会误伤。
    """
    return ".." in url.split("/")


def validate_display_link_entry(entry: Any) -> tuple[bool, str, dict]:
    """校验并规范化单条展示入口。

    Returns:
        (ok, message, normalized)；失败时 normalized 为空 dict。
    """
    if not isinstance(entry, dict):
        return False, "入口配置格式不正确", {}

    name = str(entry.get("name") or "").strip()
    if not name:
        return False, "入口缺少按钮名称", {}
    if len(name) > MAX_NAME_LEN:
        return False, f"入口的按钮名称不能超过 {MAX_NAME_LEN} 字符", {}

    link_type = str(entry.get("type") or "").strip()
    if link_type not in ENTRY_TYPES:
        return False, "入口的类型仅支持 link/text/image", {}

    if link_type == "link":
        url = str(entry.get("url") or "").strip()
        if not url:
            return False, "入口缺少链接地址", {}
        if not (url.startswith("http://") or url.startswith("https://")):
            return False, "入口的链接地址必须以 http:// 或 https:// 开头", {}
        if len(url) > MAX_URL_LEN:
            return False, f"入口的链接地址不能超过 {MAX_URL_LEN} 字符", {}
        if _has_dotdot_segment(url):
            return False, "入口的链接地址不能包含 .. 路径段", {}
        normalized = {"name": name, "type": link_type, "url": url}
        note = str(entry.get("note") or "").strip()
        if len(note) > MAX_NOTE_LEN:
            return False, f"入口的备注不能超过 {MAX_NOTE_LEN} 字符", {}
        if note:
            normalized["note"] = note
        return True, "", normalized

    if link_type == "image":
        url = str(entry.get("url") or "").strip()
        if not url:
            return False, "入口缺少图片地址", {}
        if not (
            url.startswith("/static/")
            or url.startswith("http://")
            or url.startswith("https://")
        ):
            return False, "入口的图片地址必须是 /static/ 开头的站内路径或 http(s) 链接", {}
        if len(url) > MAX_URL_LEN:
            return False, f"入口的图片地址不能超过 {MAX_URL_LEN} 字符", {}
        if _has_dotdot_segment(url):
            return False, "入口的图片地址不能包含 .. 路径段", {}
        normalized = {"name": name, "type": link_type, "url": url}
        note = str(entry.get("note") or "").strip()
        if len(note) > MAX_NOTE_LEN:
            return False, f"入口的备注不能超过 {MAX_NOTE_LEN} 字符", {}
        if note:
            normalized["note"] = note
        return True, "", normalized

    # text
    title = str(entry.get("title") or "").strip()
    if not title:
        return False, "入口缺少弹窗标题", {}
    if len(title) > MAX_TITLE_LEN:
        return False, f"入口的弹窗标题不能超过 {MAX_TITLE_LEN} 字符", {}
    # content 为多行文本，仅校验去空白后非空，存储时保留原文以不破坏换行排版
    content = str(entry.get("content") or "")
    if not content.strip():
        return False, "入口缺少弹窗内容", {}
    if len(content) > MAX_TEXT_CONTENT_LEN:
        return False, f"入口的弹窗内容不能超过 {MAX_TEXT_CONTENT_LEN} 字符", {}
    return True, "", {"name": name, "type": link_type, "title": title, "content": content}


def validate_display_links(links: Any) -> tuple[bool, str, list]:
    """校验并规范化展示入口数组（整体覆盖语义）。

    Returns:
        (ok, message, normalized_links)；失败时 normalized_links 为空列表。
    """
    if not isinstance(links, list):
        return False, "入口配置必须是数组", []
    normalized: list[dict] = []
    for index, link in enumerate(links, start=1):
        ok, message, entry = validate_display_link_entry(link)
        if not ok:
            return False, f"第 {index} 个{message}", []
        normalized.append(entry)
    return True, "", normalized


def normalize_display_links(links: Any) -> list:
    """逐条校验并规范化展示入口，丢弃非法条目。

    读取侧（提货页）专用：与 :func:`validate_display_links` 的写入侧语义相反——
    后者任一条不合法即整体拒绝，本函数只保留合法条目，避免历史脏数据阻断渲染。

    必须在 :func:`merge_display_links` **之前**调用：否则非法商品条目会先按名称占位，
    遮蔽同名默认模板。
    """
    if not isinstance(links, list):
        return []
    normalized: list[dict] = []
    for entry in links:
        ok, _, item = validate_display_link_entry(entry)
        if ok:
            normalized.append(item)
    return normalized


def merge_display_links(item_links: list, template_links: list) -> list:
    """合并商品自身条目与默认模板条目。

    入参应已由 :func:`normalize_display_links` 收敛（本函数不做字段校验）。

    规则：商品自身条目在前，默认模板在后；按名称（strip+lower）去重，商品自身优先。
    空名称条目直接跳过（脏数据兜底）。
    """
    merged: list[dict] = []
    seen: set[str] = set()
    for entry in list(item_links) + list(template_links):
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    return merged


def template_row_to_entry(template: Any) -> dict:
    """把 xy_display_link_templates 行转换为展示入口条目结构（按类型收敛字段）。"""
    link_type = str(getattr(template, "type", "") or "")
    entry: dict = {"name": getattr(template, "name", "") or "", "type": link_type}
    if link_type in ("link", "image"):
        entry["url"] = getattr(template, "url", "") or ""
        note = getattr(template, "note", "") or ""
        if note:
            entry["note"] = note
    elif link_type == "text":
        entry["title"] = getattr(template, "title", "") or ""
        entry["content"] = getattr(template, "content", "") or ""
    return entry
