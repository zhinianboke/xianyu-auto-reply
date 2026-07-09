"""
闲鱼消息内容解析（公共模块）

统一"闲鱼消息内容 JSON → (文本, 图片URL列表, 消息类型)"的解析逻辑，供以下三处
共同调用，消除历史上各写一套、互相不同步的重复实现：

1. backend-web  chat_new._parse_message        —— HTTP 拉取历史消息（content.custom.data，base64）
2. backend-web  push_message_parser._decode_content —— IM WebSocket 实时推送（["6"]["3"]["5"] 明文 / ["1"] base64）
3. websocket    message_handler.parse_chat_message  —— 自动回复引擎（同 2 的原始推送报文）

设计要点：
- 不同来源的"信封（envelope）"结构不同（HTTP 模型 vs 原始 IM 推送），信封字段的提取
  仍由各调用方自己完成；
- 一旦拿到承载消息内容的**载荷字符串**（明文 JSON 或 base64 编码的 JSON），后续
  "解码 + 判定文本/图片/语音"的核心逻辑完全一致，统一收敛到本模块。

功能：
1. load_content_json    —— 载荷字符串（明文 JSON / base64）→ 内容 dict
2. looks_like_content   —— 判断某 dict 是否为一条消息内容载荷
3. decode_first_content —— 从多个候选载荷中挑第一个"像内容"的，解析为内容 dict
4. interpret_content    —— 内容 dict → (text, images, msg_type)
5. parse_content_payloads —— 便捷组合：候选载荷列表 → (text, images, msg_type)
"""
import base64
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 已知的消息内容标识键：命中任一即认为该 dict 是一条消息内容载荷
_CONTENT_KEYS = ("text", "image", "picUrl", "audio")


def load_content_json(raw: Any) -> Optional[Dict[str, Any]]:
    """将消息内容载荷字符串解析为内容 JSON dict（兼容明文 JSON 与 base64）

    IM 实时推送的内容字段是【明文 JSON 字符串】；HTTP 历史消息与旧格式推送则是
    【base64 编码后的 JSON】。本函数先按明文 JSON 尝试，失败再按 base64 解码后解析，
    两者都失败返回 None。

    Args:
        raw: 消息内容候选值（通常为字符串）
    Returns:
        解析成功的 dict；无法解析时返回 None
    """
    if not raw or not isinstance(raw, str):
        return None

    # 1) 优先按明文 JSON 解析（实时推送为明文）
    text = raw.strip()
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    # 2) 回退按 base64 解码后解析（HTTP 历史 / 旧格式推送为 base64）
    try:
        obj = json.loads(base64.b64decode(raw).decode("utf-8"))
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    return None


def looks_like_content(obj: Any) -> bool:
    """判断解析出的 dict 是否为一条消息内容载荷

    用于在多个候选字段中挑出真正承载消息内容的那个：只要含有内容类型标记
    (contentType) 或任一已知内容键 (text/image/picUrl/audio) 即认定为内容，
    避免误把某个恰好是合法 JSON 的非内容字段当成内容。

    Args:
        obj: 待判断的值
    Returns:
        是否像消息内容
    """
    if not isinstance(obj, dict):
        return False
    return "contentType" in obj or any(k in obj for k in _CONTENT_KEYS)


def decode_first_content(candidates: Sequence[Any]) -> Optional[Dict[str, Any]]:
    """从多个候选载荷中挑第一个能解析且"像消息内容"的，返回内容 dict

    Args:
        candidates: 候选载荷字符串序列，按优先级排列
    Returns:
        第一个像内容的 dict；都不满足时返回 None
    """
    for candidate in candidates:
        decoded = load_content_json(candidate)
        if decoded is not None and looks_like_content(decoded):
            return decoded
    return None


def interpret_content(decoded: Dict[str, Any]) -> Tuple[str, List[str], str]:
    """将内容 dict 解释为 (文本, 图片URL列表, 消息类型)

    覆盖闲鱼消息的通用内容类型；与历史两套实现（chat_new._parse_message /
    push_message_parser._decode_content）保持一致：
    - contentType==1 且含 text → 文本
    - contentType==2 且含 image → 图片（取 image.pics[].url）
    - contentType==3 且含 audio → 语音（以 "[语音消息]" 文本表示）
    - 兜底：含 text → 文本；含 picUrl → 图片（旧格式）
    - 都不匹配 → 返回空类型 ""，由调用方决定降级策略

    Args:
        decoded: 已解析的内容 dict
    Returns:
        (text, images, msg_type)；msg_type ∈ {"text","image",""}
    """
    if not isinstance(decoded, dict):
        return ("", [], "")

    content_type = decoded.get("contentType", 0)

    if content_type == 1 and "text" in decoded:
        return (_extract_text(decoded["text"]), [], "text")

    if content_type == 2 and "image" in decoded:
        return ("", _extract_image_urls(decoded), "image")

    if content_type == 3 and "audio" in decoded:
        return ("[语音消息]", [], "text")

    # 兜底：未带标准 contentType 但结构可识别
    if "text" in decoded:
        return (_extract_text(decoded["text"]), [], "text")

    if "picUrl" in decoded and decoded.get("picUrl"):
        return ("", [str(decoded["picUrl"])], "image")

    return ("", [], "")


def parse_content_payloads(candidates: Sequence[Any]) -> Tuple[str, List[str], str]:
    """便捷组合：从候选载荷列表解析出 (text, images, msg_type)

    等价于 decode_first_content + interpret_content。都无法识别时返回
    ("", [], "text")，与历史推送解析的降级行为一致（交由上层用提醒文本兜底）。

    Args:
        candidates: 候选载荷字符串序列，按优先级排列
    Returns:
        (text, images, msg_type)
    """
    decoded = decode_first_content(candidates)
    if decoded is None:
        return ("", [], "text")
    text, images, msg_type = interpret_content(decoded)
    return (text, images, msg_type or "text")


def _extract_text(text_obj: Any) -> str:
    """从 text 字段提取纯文本（text 可能是 {"text": "..."} 或直接字符串）"""
    if isinstance(text_obj, dict):
        return str(text_obj.get("text", ""))
    return str(text_obj)


def _extract_image_urls(decoded: Dict[str, Any]) -> List[str]:
    """从图片内容 dict 提取所有图片 URL（image.pics[].url）"""
    pics = decoded.get("image", {}).get("pics", [])
    if not isinstance(pics, list):
        return []
    return [p.get("url", "") for p in pics if isinstance(p, dict) and p.get("url")]
