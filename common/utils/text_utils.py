"""
文本处理通用工具

功能:
1. XSS 转义 - 对外部输入文本进行 HTML 实体转义，防止跨站脚本注入

注意: 此模块只放与文本处理相关的纯函数，与密码哈希/JWT 无关。
密码哈希、JWT 令牌等安全功能请放在 ``common/utils/security.py``。
"""
from __future__ import annotations

import html


def escape_xss(text: str | None) -> str | None:
    """对文本进行 HTML 实体转义，防止 XSS 注入。

    Args:
        text: 待转义的原始文本，允许为 ``None`` 或空字符串。

    Returns:
        转义后的安全文本；当 ``text`` 为 ``None`` 或空时原样返回，便于上层链式处理。
    """
    if not text:
        return text
    return html.escape(text)


__all__ = ["escape_xss"]
