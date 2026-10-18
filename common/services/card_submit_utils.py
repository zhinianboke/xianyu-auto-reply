"""
卡密提交与通知的公共解析工具。

功能：
1. 从订单发货内容提取 CFM0/CFM1 卡密并去重
2. 解析卡密提交接口的 JSON 返回值
3. 按统一格式拼接通知买家的消息
"""
from __future__ import annotations

import json
import re
from typing import Any


CARD_CODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])CFM[01](?:-[A-Za-z0-9]+)+(?![A-Za-z0-9-])",
    re.IGNORECASE,
)
MAX_CODES_PER_REQUEST = 248


def extract_card_codes(delivery_content: str | None) -> list[str]:
    """从发货内容提取最多 32 个字符的 CFM0/CFM1 卡密并保持原顺序去重。"""
    seen: set[str] = set()
    codes: list[str] = []
    for matched in CARD_CODE_PATTERN.findall(delivery_content or ""):
        code = matched.upper()
        if len(code) > 32 or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def parse_response_body(response_body: str | dict[str, Any]) -> dict[str, Any]:
    """把提交日志中的返回值解析为字典，格式无效时返回空字典。"""
    if isinstance(response_body, dict):
        return response_body
    try:
        value = json.loads(response_body)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def build_card_submit_notification(order_no: str, response_body: str | dict[str, Any]) -> str | None:
    """按卡密提交返回值中的 cards 列表生成买家通知消息。"""
    response = parse_response_body(response_body)
    # 卡密提交日志同时保存 request/response 时，实际接口返回值位于 response 节点。
    if not isinstance(response.get("cards"), list) and isinstance(response.get("response"), dict):
        response = response["response"]
    cards = response.get("cards")
    if not isinstance(cards, list):
        return None

    lines = [f"尊敬的买家，您的订单{order_no}处理结果如下："]
    for item in cards:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        status = str(item.get("status") or "").strip()
        if code and status:
            lines.append(f"卡密{code}：结果：{status}")
    return "\n".join(lines) if len(lines) > 1 else None


def serialize_response_body(response: Any) -> str:
    """完整序列化接口返回值，无法 JSON 序列化时保留原始字符串。"""
    try:
        return json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(response)
