"""
商品通用查询 - 模板与变量纯函数模块

功能：
1. extract_card_variables：从卡密行提取固定四变量（account / api_key / cookie / line）
2. render_template：将 URL/请求头/Body 模板中的 ``{var}`` 占位符替换为变量值
3. resolve_path：按点路径从响应 JSON 中取值（数字段作数组下标）
4. mask_account：账号脱敏（仅展示需要，绝不回传完整账号）

说明：
- 本模块不依赖 fastapi / sqlalchemy / httpx，仅使用标准库，可被任意服务直接引用。
- 变量名固定四种：``{cookie}`` ``{account}`` ``{api_key}`` ``{line}``，
  与 ``xy_catalog_items.metadata_json.query_buttons`` 配置契约一致。
"""
from __future__ import annotations

import re
from typing import Any

# 卡密行格式：账号：xxx API Key：xxx 余额：xxx Cookie：<完整字符串>
_ACCOUNT_RE = re.compile(r"账号[：:]\s*(\S+)")
_API_KEY_RE = re.compile(r"API\s*Key[：:]\s*(\S+)")
_COOKIE_RE = re.compile(r"Cookie[：:]\s*(.+)$")
# 模板变量占位符：{var}，变量名为字母/数字/下划线
_TEMPLATE_VAR_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")


def extract_card_variables(line: str) -> dict[str, str]:
    """从单行卡密内容提取固定四变量。

    Args:
        line: 发货内容中的单行文本。

    Returns:
        ``{"account": ..., "api_key": ..., "cookie": ..., "line": ...}``；
        缺失的变量为空串；``line`` 为整行 strip 后的原文。
    """
    text = (line or "").strip()
    account_match = _ACCOUNT_RE.search(text)
    api_key_match = _API_KEY_RE.search(text)
    cookie_match = _COOKIE_RE.search(text)
    return {
        "account": account_match.group(1) if account_match else "",
        "api_key": api_key_match.group(1) if api_key_match else "",
        "cookie": cookie_match.group(1).strip() if cookie_match else "",
        "line": text,
    }


def render_template(template: str | None, variables: dict[str, str]) -> str | None:
    """将模板中的 ``{var}`` 占位符替换为变量值。

    未知变量（variables 中不存在的占位符）原样保留，便于排查配置错误；
    template 为 None 时原样返回 None（如 GET 请求无 body）。
    """
    if template is None:
        return None

    def _replace(match: re.Match) -> str:
        name = match.group(1)
        if name in variables:
            return str(variables[name])
        return match.group(0)

    return _TEMPLATE_VAR_RE.sub(_replace, template)


def resolve_path(payload: Any, path: str) -> Any:
    """按点路径从 JSON 结构中取值，如 ``data.list.0.name``（数字段作数组下标）。

    路径为空时返回 payload 本身；任何一段解析失败（键不存在 / 下标越界 /
    类型不匹配）均返回 None，调用方按"取不到值"处理。
    """
    if not path:
        return payload
    current = payload
    for segment in str(path).split("."):
        if isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
        elif isinstance(current, (list, tuple)):
            if not segment.isdigit():
                return None
            index = int(segment)
            if index >= len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def mask_account(account: str | None) -> str | None:
    """账号脱敏：>=7 位保留前3后4，>1 位保留首字符，否则返回 ``***``；None 原样返回。"""
    if account is None:
        return None
    text = str(account)
    if len(text) >= 7:
        return f"{text[:3]}****{text[-4:]}"
    if len(text) > 1:
        return f"{text[0]}***"
    return "***"


def template_url_has_variable_host(url: str | None) -> bool:
    """判断 URL 模板的 host 段（netloc）是否含 ``{...}`` 变量占位符。

    变量只允许出现在 path/query/headers/body：若 host 段可渲染，
    买家可通过 cookie_override 注入任意字符串让服务器请求任意地址（SSRF）。
    URL 解析失败按危险处理（返回 True）。
    """
    from urllib.parse import urlsplit

    if not url:
        return True
    try:
        return "{" in urlsplit(str(url)).netloc
    except Exception:
        return True
