"""
AI 文本生成通用客户端

功能：
1. 封装 OpenAI 兼容的 /chat/completions 调用，供 AI 铺货等"一次性文本生成"场景复用
2. 处理部分模型对 content 形态与思考模式的兼容差异（收到 400 时自动降级重试）
3. 区分可重试错误（网络异常/429/5xx）与不可重试错误（401/403/参数错误），避免无意义重试

说明：
- 与 websocket 侧的 AI 回复引擎相互独立：那边带会话上下文与议价逻辑，
  这里只做"给一段提示词、拿一段文本"的无状态调用。
- 密钥仅用于请求头，日志中只记录长度，不记录明文，也不记录完整请求地址。
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx
from loguru import logger

from common.services.ai_provider_service import build_openai_url, extract_response_error

# 默认请求超时（秒）：文案生成通常在 10~60 秒之间
DEFAULT_TEXT_TIMEOUT = 90.0

# 可重试错误的最大重试次数与退避基数（秒）
MAX_RETRY_TIMES = 2
RETRY_BACKOFF_SECONDS = 1.0

# 可重试的 HTTP 状态码：请求超时、限流与服务端错误
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


class AiCallError(RuntimeError):
    """AI 接口调用失败

    Attributes:
        message: 中文错误消息，可直接展示给用户。
        retryable: 是否值得重试（网络抖动、限流、服务端错误）。
        status_code: 第三方接口返回的 HTTP 状态码；网络异常时为 None。
    """

    def __init__(self, message: str, *, retryable: bool = False, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.status_code = status_code


def _messages_to_array_content(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把消息里的字符串 content 转成数组形态

    部分多模态/全模态模型只接受 ``content: [{"type": "text", "text": "..."}]``，
    字符串形态会被判 400，需要降级重试。

    Args:
        messages: 原始消息列表。
    Returns:
        content 已转为数组形态的新消息列表（不修改入参）。
    """
    converted: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            converted.append({**message, "content": [{"type": "text", "text": content}]})
        else:
            converted.append(dict(message))
    return converted


def _build_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    disable_thinking: bool,
) -> dict[str, Any]:
    """组装 chat/completions 请求体

    Args:
        model: 模型名称。
        messages: 消息列表。
        temperature: 采样温度。
        max_tokens: 最大生成 token 数。
        disable_thinking: 是否显式关闭思考模式（qwen3 等模型需要，否则思考过程会挤占正文）。
    Returns:
        请求体字典。
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if disable_thinking:
        payload["enable_thinking"] = False
    return payload


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """发一次 POST 请求并把失败统一转成 AiCallError

    这里不复用 ai_provider_service.ensure_success_response：它会把完整请求地址写进日志，
    部分中转网关把密钥放在 URL 上，容易泄漏。

    Args:
        client: httpx 异步客户端。
        url: 完整请求地址。
        headers: 请求头。
        payload: JSON 请求体。
        timeout: 超时秒数。
    Returns:
        响应体 JSON。
    Raises:
        AiCallError: 网络异常、非 2xx 响应或响应体不是 JSON。
    """
    try:
        response = await client.post(url, headers=headers, json=payload, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise AiCallError("AI接口请求超时，请稍后重试", retryable=True) from exc
    except httpx.HTTPError as exc:
        raise AiCallError(f"AI接口连接失败：{exc}", retryable=True) from exc

    if 200 <= response.status_code < 300:
        try:
            return response.json()
        except Exception as exc:
            raise AiCallError("AI接口返回内容不是合法的JSON") from exc

    detail = extract_response_error(response)
    raise AiCallError(
        f"AI接口返回HTTP {response.status_code}：{detail}",
        retryable=response.status_code in RETRYABLE_STATUS_CODES,
        status_code=response.status_code,
    )



def _extract_content(data: dict[str, Any]) -> str:
    """从响应体中取出模型输出的文本

    Args:
        data: chat/completions 响应体。
    Returns:
        去除首尾空白的文本内容。
    Raises:
        AiCallError: 没有 choices 或内容为空。
    """
    choices = data.get("choices") or []
    if not choices:
        raise AiCallError("AI接口未返回任何结果")

    message = (choices[0] or {}).get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        # 数组 content 形态：拼接所有文本片段
        content = "".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        )

    text = str(content or "").strip()
    if not text:
        raise AiCallError("AI接口返回内容为空")
    return text


async def request_json_with_retries(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    *,
    label: str = "AI接口",
) -> dict[str, Any]:
    """带退避重试的 POST：只重试网络异常/限流/服务端错误

    401/403/400、以及响应体不是 JSON 这类问题重试也不会变，直接抛出。

    Args:
        client: httpx 异步客户端。
        url: 完整请求地址。
        headers: 请求头。
        payload: JSON 请求体。
        timeout: 超时秒数。
        label: 日志里显示的接口名称（如"文案接口"/"图片接口"）。
    Returns:
        响应体 JSON。
    Raises:
        AiCallError: 重试用尽或遇到不可重试错误。
    """
    last_error: Optional[AiCallError] = None
    for attempt in range(MAX_RETRY_TIMES + 1):
        try:
            return await post_json(client, url, headers, payload, timeout)
        except AiCallError as exc:
            last_error = exc
            if not exc.retryable or attempt >= MAX_RETRY_TIMES:
                raise
            delay = RETRY_BACKOFF_SECONDS * (2 ** attempt)
            logger.warning(
                f"【AI铺货】{label}调用失败，{delay:.0f}秒后重试（第{attempt + 1}次）：{exc.message}"
            )
            await asyncio.sleep(delay)
    # 循环必然在上面 return 或 raise，这里只是兜底让类型检查满意
    raise last_error or AiCallError(f"{label}调用失败")



async def chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: float = DEFAULT_TEXT_TIMEOUT,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    """调用 OpenAI 兼容的 chat/completions 生成文本

    收到 400 时按"字符串content+关闭思考 → 字符串content → 数组content+关闭思考 → 数组content"
    四种形态依次降级，兼容 qwen3、多模态模型等对请求体的不同要求。

    Args:
        base_url: 接口基础地址（会自动剥掉 /chat/completions 等后缀）。
        api_key: 接口密钥，仅用于 Authorization 头。
        model: 模型名称。
        messages: OpenAI 格式消息列表。
        temperature: 采样温度。
        max_tokens: 最大生成 token 数。
        timeout: 单次请求超时（秒）。
        client: 复用的 httpx 客户端；为 None 时内部自建并在结束后关闭。

    Returns:
        模型输出的文本。

    Raises:
        AiCallError: 所有兼容形态都失败，或遇到不可重试错误。
    """
    url = build_openai_url(base_url, "/chat/completions")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    array_messages = _messages_to_array_content(messages)
    # (说明, 消息体, 是否关闭思考, 是否允许退避重试)
    # 只有第一种形态做重试，避免"4 种形态 × 3 次请求"把单次生成拖到十几分钟
    attempts = (
        ("字符串content+关闭思考", messages, True, True),
        ("字符串content", messages, False, False),
        ("数组content+关闭思考", array_messages, True, False),
        ("数组content", array_messages, False, False),
    )

    logger.info(f"【AI铺货】调用文案接口 model={model} api_key长度={len(api_key or '')}")

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout)
    try:
        last_error: Optional[AiCallError] = None
        for label, payload_messages, disable_thinking, allow_retry in attempts:
            payload = _build_payload(
                model=model,
                messages=payload_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                disable_thinking=disable_thinking,
            )
            try:
                if allow_retry:
                    data = await request_json_with_retries(
                        http_client, url, headers, payload, timeout, label="文案接口"
                    )
                else:
                    data = await post_json(http_client, url, headers, payload, timeout)
            except AiCallError as exc:
                last_error = exc
                if exc.status_code == 400:
                    logger.info(f"【AI铺货】{label} 被模型拒绝，尝试下一种兼容形态 model={model}")
                    continue
                raise
            return _extract_content(data)
        raise last_error or AiCallError("AI接口调用失败")
    finally:
        if owns_client:
            await http_client.aclose()


__all__ = [
    "AiCallError",
    "DEFAULT_TEXT_TIMEOUT",
    "chat_completion",
    "post_json",
    "request_json_with_retries",
]



