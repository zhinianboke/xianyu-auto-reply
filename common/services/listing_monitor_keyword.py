"""
商品监控 - 多关键词拆分与标题/内容匹配

功能：
1. 将任务关键字按空格/逗号/分号拆成多个词
2. 按匹配模式（off/any/all）判断「标题或内容」是否命中（二者任一出现即算该词命中）
3. 开启本地匹配时，搜索接口使用首个关键词，避免整串空格被平台模糊搜偏
"""
from __future__ import annotations

import re
from typing import List, Optional

# 支持的匹配模式
KEYWORD_MATCH_OFF = "off"
KEYWORD_MATCH_ANY = "any"
KEYWORD_MATCH_ALL = "all"
KEYWORD_MATCH_MODES = (KEYWORD_MATCH_OFF, KEYWORD_MATCH_ANY, KEYWORD_MATCH_ALL)

# 空格、英文/中文逗号分号
_SPLIT_RE = re.compile(r"[\s,，;；]+")


def normalize_keyword_match_mode(mode: Optional[str]) -> str:
    """规整匹配模式，非法值回退为 off。"""
    value = (mode or KEYWORD_MATCH_OFF).strip().lower()
    return value if value in KEYWORD_MATCH_MODES else KEYWORD_MATCH_OFF


def split_monitor_keywords(keyword: Optional[str]) -> List[str]:
    """拆分关键字；去空、保序、去重（大小写不敏感去重，保留首次写法）。"""
    text = (keyword or "").strip()
    if not text:
        return []
    seen = set()
    result: List[str] = []
    for part in _SPLIT_RE.split(text):
        token = part.strip()
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(token)
    return result


def resolve_search_keyword(keyword: Optional[str], match_mode: Optional[str]) -> str:
    """决定传给闲鱼搜索接口的 keyword。

    - off：整串原样（兼容旧行为）
    - any/all：用首个词搜索，再在本地按标题/内容过滤
    """
    text = (keyword or "").strip()
    mode = normalize_keyword_match_mode(match_mode)
    if mode == KEYWORD_MATCH_OFF:
        return text
    parts = split_monitor_keywords(text)
    return parts[0] if parts else text


def _build_match_haystack(title: Optional[str], content: Optional[str]) -> str:
    """合并标题与内容作为匹配文本（词可出现在任一处）。"""
    parts = [str(title or "").strip(), str(content or "").strip()]
    return "\n".join(p for p in parts if p).casefold()


def item_matches_keywords(
    title: Optional[str],
    content: Optional[str],
    keyword: Optional[str],
    match_mode: Optional[str],
) -> bool:
    """按匹配模式判断标题或内容是否命中关键字。

    每个关键词只要在标题或内容任一处出现即算命中该词：
    - off：始终 True（不做本地过滤）
    - any：任一关键词命中即可
    - all：全部关键词都要命中
    """
    mode = normalize_keyword_match_mode(match_mode)
    if mode == KEYWORD_MATCH_OFF:
        return True
    parts = split_monitor_keywords(keyword)
    if not parts:
        return True
    haystack = _build_match_haystack(title, content)
    if not haystack:
        return False
    needles = [p.casefold() for p in parts]
    if mode == KEYWORD_MATCH_ALL:
        return all(n in haystack for n in needles)
    return any(n in haystack for n in needles)


def title_matches_keywords(
    title: Optional[str],
    keyword: Optional[str],
    match_mode: Optional[str],
) -> bool:
    """兼容旧调用：仅传标题时等价于无内容的 item_matches_keywords。"""
    return item_matches_keywords(title, None, keyword, match_mode)


__all__ = [
    "KEYWORD_MATCH_OFF",
    "KEYWORD_MATCH_ANY",
    "KEYWORD_MATCH_ALL",
    "KEYWORD_MATCH_MODES",
    "normalize_keyword_match_mode",
    "split_monitor_keywords",
    "resolve_search_keyword",
    "item_matches_keywords",
    "title_matches_keywords",
]
