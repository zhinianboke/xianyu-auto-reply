"""
AI服务商工具

功能：
1. 统一AI服务商类型识别
2. 按服务商协议获取模型列表
3. 按服务商协议测试AI连接
"""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger


DEFAULT_AI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_AI_PROVIDER_TYPE = "openai_compatible"
VALID_AI_PROVIDER_TYPES = {
    "openai_compatible",
    "anthropic",
    "gemini",
    "dashscope_app",
}
AI_PROVIDER_NAMES = {
    "openai_compatible": "OpenAI兼容",
    "anthropic": "Anthropic Claude",
    "gemini": "Google Gemini",
    "dashscope_app": "DashScope应用",
}

AI_PROVIDER_DEFAULT_BASE_URLS = {
    "openai_compatible": DEFAULT_AI_BASE_URL,
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "dashscope_app": "https://dashscope.aliyuncs.com/api/v1/apps/{app_id}/completion",
}


def clean_ai_text(value: Any) -> str:
    """清理AI配置文本中的危险换行和首尾空白"""
    return str(value or "").replace("\r", "").replace("\n", "").strip()


def normalize_ai_provider_type(
    provider_type: Any = None,
    base_url: Any = "",
    model_name: Any = "",
) -> str:
    """规范化AI服务商类型，兼容旧配置没有服务商字段的场景"""
    provider = clean_ai_text(provider_type).lower().replace("-", "_")
    aliases = {
        "openai": "openai_compatible",
        "openai_compatible": "openai_compatible",
        "openai兼容": "openai_compatible",
        "dashscope_compatible": "openai_compatible",
        "qwen": "openai_compatible",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "gemini": "gemini",
        "google_gemini": "gemini",
        "dashscope_app": "dashscope_app",
        "dashscope应用": "dashscope_app",
    }
    if provider in aliases:
        return aliases[provider]
    if provider in VALID_AI_PROVIDER_TYPES:
        return provider

    base = clean_ai_text(base_url).lower()
    model = clean_ai_text(model_name).lower()
    if "dashscope.aliyuncs.com" in base and "/apps/" in base:
        return "dashscope_app"
    if "generativelanguage.googleapis.com" in base:
        return "gemini"
    if "api.anthropic.com" in base:
        return "anthropic"
    if provider == "dashscope" and "/apps/" in base:
        return "dashscope_app"
    if provider == "dashscope":
        return "openai_compatible"
    if not base and "gemini" in model:
        return "gemini"
    if not base and "claude" in model:
        return "anthropic"
    return DEFAULT_AI_PROVIDER_TYPE


def get_ai_provider_name(provider_type: Any = None, base_url: Any = "", model_name: Any = "") -> str:
    """获取AI服务商中文名称"""
    provider = normalize_ai_provider_type(provider_type, base_url, model_name)
    base = clean_ai_text(base_url).lower()
    model = clean_ai_text(model_name).lower()
    if provider != "openai_compatible":
        return AI_PROVIDER_NAMES.get(provider, "OpenAI兼容")

    provider_map = {
        "api.openai.com": "OpenAI",
        "dashscope.aliyuncs.com": "阿里云百炼兼容模式",
        "open.bigmodel.cn": "智谱AI",
        "api.moonshot.cn": "Moonshot/Kimi",
        "api.deepseek.com": "DeepSeek",
        "api.lingyiwanwu.com": "零一万物",
        "api.siliconflow.cn": "硅基流动",
        "api.groq.com": "Groq",
        "api.together.xyz": "Together AI",
        "aip.baidubce.com": "百度文心",
        "localhost": "本地部署",
        "127.0.0.1": "本地部署",
    }
    for domain, name in provider_map.items():
        if domain in base:
            return name
    if "gpt" in model:
        return "OpenAI兼容"
    if "qwen" in model:
        return "通义千问"
    if "glm" in model:
        return "智谱AI"
    if "deepseek" in model:
        return "DeepSeek"
    if "claude" in model:
        return "Claude中转"
    if "gemini" in model:
        return "Gemini中转"
    return "OpenAI兼容"


def get_default_ai_base_url(provider_type: Any = None) -> str:
    """获取服务商默认API地址"""
    provider = normalize_ai_provider_type(provider_type)
    return AI_PROVIDER_DEFAULT_BASE_URLS.get(provider, DEFAULT_AI_BASE_URL)


def read_ai_enabled(ai_settings: dict[str, Any] | None) -> bool:
    """读取AI启用状态，兼容历史enabled字段"""
    settings = ai_settings or {}
    value = settings.get("ai_enabled")
    if value is None:
        value = settings.get("enabled", False)
    return bool(value)


def normalize_ai_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    """规范化AI设置字典"""
    payload = dict(settings or {})
    provider_type = normalize_ai_provider_type(
        payload.get("provider_type"),
        payload.get("base_url"),
        payload.get("model_name"),
    )
    payload["provider_type"] = provider_type
    payload["api_key"] = clean_ai_text(payload.get("api_key"))
    payload["base_url"] = clean_ai_text(payload.get("base_url")) or get_default_ai_base_url(provider_type)
    payload["model_name"] = clean_ai_text(payload.get("model_name")) or "qwen-plus"
    return payload


def get_ai_settings_missing_fields(settings: dict[str, Any] | None) -> list[str]:
    """获取启用AI前必须补全的配置字段"""
    payload = dict(settings or {})
    provider = normalize_ai_provider_type(
        payload.get("provider_type"),
        payload.get("base_url"),
        payload.get("model_name"),
    )
    base_url = clean_ai_text(payload.get("base_url"))
    api_key = clean_ai_text(payload.get("api_key"))
    model_name = clean_ai_text(payload.get("model_name"))
    missing_fields: list[str] = []
    if not base_url:
        missing_fields.append("API地址")
    if not api_key:
        missing_fields.append("API Key")
    if provider != "dashscope_app" and not model_name:
        missing_fields.append("模型名称")
    if provider == "dashscope_app" and ("{app_id}" in base_url or "/apps/" not in base_url):
        missing_fields.append("DashScope应用地址")
    return missing_fields


def normalize_openai_base_url(base_url: str) -> str:
    """规范化OpenAI兼容接口基础地址"""
    base = clean_ai_text(base_url) or DEFAULT_AI_BASE_URL
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    if base.endswith("/models"):
        base = base[: -len("/models")]
    return base


def build_openai_url(base_url: str, path: str) -> str:
    """拼接OpenAI兼容接口地址"""
    base = normalize_openai_base_url(base_url)
    return f"{base}/{path.lstrip('/')}"


def build_anthropic_url(base_url: str, path: str) -> str:
    """拼接Anthropic官方接口地址"""
    base = (clean_ai_text(base_url) or AI_PROVIDER_DEFAULT_BASE_URLS["anthropic"]).rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/{path.lstrip('/')}"
    return f"{base}/v1/{path.lstrip('/')}"


def build_gemini_url(base_url: str, path: str) -> str:
    """拼接Gemini官方接口地址"""
    base = (clean_ai_text(base_url) or AI_PROVIDER_DEFAULT_BASE_URLS["gemini"]).rstrip("/")
    if base.endswith("/v1beta") or base.endswith("/v1"):
        return f"{base}/{path.lstrip('/')}"
    return f"{base}/v1beta/{path.lstrip('/')}"


def extract_response_error(response: httpx.Response) -> str:
    """提取第三方接口错误消息"""
    try:
        body = response.json()
    except Exception:
        body_text = response.text or ""
        return body_text[:500] if body_text else f"HTTP {response.status_code}"

    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("type") or error)[:500]
        if isinstance(error, str):
            return error[:500]
        for key in ("message", "msg", "detail"):
            if body.get(key):
                return str(body[key])[:500]
    return str(body)[:500]


def ensure_success_response(response: httpx.Response, provider_name: str) -> None:
    """检查第三方接口响应状态"""
    if 200 <= response.status_code < 300:
        return
    error_detail = extract_response_error(response)
    logger.warning(
        f"【AI接口】{provider_name} 调用失败 status={response.status_code} url={response.request.url} body={error_detail}"
    )
    raise RuntimeError(f"{provider_name}返回HTTP {response.status_code}: {error_detail}")


def normalize_model_options(models: list[dict[str, Any]]) -> list[dict[str, str]]:
    """规范化模型选项"""
    seen: set[str] = set()
    options: list[dict[str, str]] = []
    for model in models:
        model_id = clean_ai_text(model.get("id") or model.get("name") or model.get("model"))
        if model_id.startswith("models/"):
            model_id = model_id.split("/", 1)[1]
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        display_name = clean_ai_text(model.get("display_name") or model.get("displayName") or model.get("name"))
        if display_name.startswith("models/"):
            display_name = model_id
        options.append({"id": model_id, "name": display_name or model_id})
    return options


async def fetch_ai_model_list(provider_type: Any, base_url: Any, api_key: Any) -> list[dict[str, str]]:
    """按服务商协议获取模型列表"""
    settings = normalize_ai_settings({"provider_type": provider_type, "base_url": base_url, "api_key": api_key})
    provider = settings["provider_type"]
    key = settings["api_key"]
    if not key:
        raise ValueError("请先填写API Key")

    if provider == "dashscope_app":
        raise ValueError("DashScope应用API不支持自动获取模型列表，请手动填写模型名称")

    async with httpx.AsyncClient(timeout=30.0) as client:
        if provider == "anthropic":
            url = build_anthropic_url(settings["base_url"], "/models")
            response = await client.get(
                url,
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
            )
            ensure_success_response(response, get_ai_provider_name(provider, settings["base_url"]))
            result = response.json()
            data = result.get("data", []) if isinstance(result, dict) else []
            return normalize_model_options(data if isinstance(data, list) else [])

        if provider == "gemini":
            url = build_gemini_url(settings["base_url"], "/models")
            response = await client.get(url, params={"key": key})
            ensure_success_response(response, get_ai_provider_name(provider, settings["base_url"]))
            result = response.json()
            data = result.get("models", []) if isinstance(result, dict) else []
            if isinstance(data, list):
                data = [
                    item for item in data
                    if not isinstance(item, dict)
                    or "supportedGenerationMethods" not in item
                    or "generateContent" in item.get("supportedGenerationMethods", [])
                ]
            return normalize_model_options(data if isinstance(data, list) else [])

        url = build_openai_url(settings["base_url"], "/models")
        response = await client.get(url, headers={"Authorization": f"Bearer {key}"})
        ensure_success_response(response, get_ai_provider_name(provider, settings["base_url"]))
        result = response.json()
        if isinstance(result, dict):
            data = result.get("data") or result.get("models") or []
        elif isinstance(result, list):
            data = result
        else:
            data = []
        return normalize_model_options(data if isinstance(data, list) else [])


async def test_ai_connection(
    provider_type: Any,
    base_url: Any,
    api_key: Any,
    model_name: Any,
) -> str:
    """按服务商协议测试AI连接"""
    raw_settings = {
        "provider_type": provider_type,
        "base_url": base_url,
        "api_key": api_key,
        "model_name": model_name,
    }
    missing_fields = get_ai_settings_missing_fields(raw_settings)
    if missing_fields:
        raise ValueError(f"AI配置未填写完整，请先补全：{'、'.join(missing_fields)}")

    settings = normalize_ai_settings(raw_settings)
    provider = settings["provider_type"]
    key = settings["api_key"]
    model = settings["model_name"]
    if not key:
        raise ValueError("未配置API Key，请先配置AI设置")

    max_tokens = 100
    temperature = 0.7
    messages = [
        {"role": "system", "content": "你是AI连接测试助手。"},
        {"role": "user", "content": "你好，请回复'测试成功'"},
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        if provider == "anthropic":
            url = build_anthropic_url(settings["base_url"], "/messages")
            system_content = ""
            user_messages: list[dict[str, str]] = []
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "system":
                    system_content = content
                elif role in ("user", "assistant"):
                    user_messages.append({"role": role, "content": content})
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": user_messages or [{"role": "user", "content": ""}],
            }
            if system_content:
                payload["system"] = system_content
            response = await client.post(
                url,
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            ensure_success_response(response, get_ai_provider_name(provider, settings["base_url"], model))
            result = response.json()
            content = result.get("content", []) if isinstance(result, dict) else []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                    return clean_ai_text(item["text"])
            raise RuntimeError(f"Anthropic响应格式错误: {str(result)[:500]}")

        if provider == "gemini":
            url = build_gemini_url(settings["base_url"], f"/models/{model}:generateContent")
            system_instruction = ""
            user_content_parts: list[str] = []
            for msg in messages:
                if msg["role"] == "system":
                    system_instruction = msg["content"]
                elif msg["role"] == "user":
                    user_content_parts.append(msg["content"])
            user_content = "\n".join(user_content_parts)
            if not user_content:
                raise ValueError("未在消息中找到用户内容")
            payload = {
                "contents": [{"role": "user", "parts": [{"text": user_content}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            }
            if system_instruction:
                payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
            response = await client.post(
                url,
                params={"key": key},
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            ensure_success_response(response, get_ai_provider_name(provider, settings["base_url"], model))
            result = response.json()
            try:
                return clean_ai_text(result["candidates"][0]["content"]["parts"][0]["text"])
            except Exception as exc:
                raise RuntimeError(f"Gemini响应格式错误: {str(result)[:500]}") from exc

        if provider == "dashscope_app":
            base = settings["base_url"]
            if "/apps/" not in base:
                raise ValueError("DashScope应用API地址中未找到app_id")
            app_id = base.split("/apps/", 1)[1].split("/", 1)[0]
            url = f"https://dashscope.aliyuncs.com/api/v1/apps/{app_id}/completion"
            system_content = ""
            user_content = ""
            for msg in messages:
                if msg["role"] == "system":
                    system_content = msg["content"]
                elif msg["role"] == "user":
                    user_content = msg["content"]
            if system_content and user_content:
                prompt = f"{system_content}\n\n用户问题：{user_content}\n\n请直接回答用户的问题："
            elif user_content:
                prompt = user_content
            else:
                prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "input": {"prompt": prompt},
                    "parameters": {"max_tokens": max_tokens, "temperature": temperature},
                    "debug": {},
                },
            )
            ensure_success_response(response, get_ai_provider_name(provider, settings["base_url"], model))
            result = response.json()
            try:
                return clean_ai_text(result["output"]["text"])
            except Exception as exc:
                raise RuntimeError(f"DashScope应用响应格式错误: {str(result)[:500]}") from exc

        url = build_openai_url(settings["base_url"], "/chat/completions")
        # 优先使用字符串 content（兼容性最广），失败后回退到数组形式（兼容omni等多模态模型）
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        response = await client.post(
            url,
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        if response.status_code == 400:
            # 多模态/全模态模型可能要求 content 为数组格式，回退重试
            logger.info(f"【AI接口】OpenAI兼容 字符串content被拒绝，尝试数组content格式 model={model}")
            converted_messages = []
            for msg in messages:
                content = msg.get("content")
                if isinstance(content, str):
                    converted_messages.append({**msg, "content": [{"type": "text", "text": content}]})
                else:
                    converted_messages.append(msg)
            response = await client.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "messages": converted_messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
        ensure_success_response(response, get_ai_provider_name(provider, settings["base_url"], model))
        result = response.json()
        try:
            return clean_ai_text(result["choices"][0]["message"]["content"])
        except Exception as exc:
            raise RuntimeError(f"OpenAI兼容响应格式错误: {str(result)[:500]}") from exc
