"""API关键词HTTP请求，复用卡券响应取值及递归参数替换，不携带闲鱼Cookie。"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import unquote_plus

import httpx
from loguru import logger

from common.models.xy_api_keyword_rule import HTTP_METHODS
from common.services.api_keyword_params import build_api_keyword_params
from common.utils.response_field import (
    RESPONSE_FIELD_EMPTY_MESSAGE,
    extract_card_api_response_content,
)


class ApiKeywordRequestError(ValueError):
    """API请求或响应取值失败，错误消息可直接展示。"""


def _query_params(params: dict[str, Any]) -> dict[str, Any]:
    """把GET中的嵌套JSON、布尔及空值转换为查询字符串，普通字符串和数字保持原值。"""
    return {
        key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list, bool)) or value is None else value
        for key, value in params.items()
    }


def _get_request_url(url: str, params: dict[str, Any]) -> httpx.URL:
    """追加编码后的GET参数，覆盖同名参数，并保留其他查询片段的原编码与顺序。"""
    parsed = httpx.URL(url)
    if not params:
        return parsed
    original = [
        part for part in parsed.query.split(b"&")
        if unquote_plus(part.partition(b"=")[0].decode("ascii")) not in params
    ]
    encoded = str(httpx.QueryParams(_query_params(params))).encode("ascii")
    existing = b"&".join(original)
    separator = b"&" if existing and not existing.endswith(b"&") else b""
    return parsed.copy_with(query=existing + separator + encoded)


async def request_api_keyword(config: dict[str, Any], item_id: str, message: str) -> str:
    """按配置请求一次API并返回卡券兼容取值；避免POST自动重试造成第三方重复操作。"""
    method = str(config["method"]).upper()
    if method not in HTTP_METHODS:
        raise ApiKeywordRequestError("API关键词请求方法无效，仅支持GET和POST")
    timeout = int(config["timeout"])
    if not 1 <= timeout <= 300:
        raise ApiKeywordRequestError("API关键词超时时间必须为1至300秒")
    params = build_api_keyword_params(config.get("params") or {}, item_id, message)
    headers = dict(config.get("headers") or {})
    if method == "POST" and not any(key.casefold() == "content-type" for key in headers):
        headers["Content-Type"] = "application/json"
    kwargs = {} if method == "GET" else {"json": params}
    request = {"method": method, "url": config["url"], "headers": headers, "params": None, "body": kwargs.get("json")}
    response: dict[str, Any] = {"status": None, "headers": None, "body": None}
    logger.info("API关键词开始请求: rule_id={}, request={}", config["id"], request)
    try:
        outgoing_url = _get_request_url(config["url"], params) if method == "GET" else config["url"]
        if method == "GET":
            request.update(url=str(outgoing_url), params=list(outgoing_url.params.multi_items()))
        # HTTPX默认不重试连接；总超时同时覆盖建连、读取及整个响应传输。
        async with asyncio.timeout(timeout), httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            outgoing = client.build_request(method, outgoing_url, headers=headers, **kwargs)
            request.update(url=str(outgoing.url), headers=dict(outgoing.headers))
            result = await client.send(outgoing)
            response.update(status=result.status_code, headers=dict(result.headers), body=result.text)
            if not 200 <= result.status_code < 300:
                raise ApiKeywordRequestError(f"API关键词请求失败，HTTP状态码：{result.status_code}")
            content = extract_card_api_response_content(response["body"], config.get("response_field"))
            if content == RESPONSE_FIELD_EMPTY_MESSAGE or not content.strip():
                raise ApiKeywordRequestError(RESPONSE_FIELD_EMPTY_MESSAGE)
            logger.info("API关键词请求成功: rule_id={}, response={}", config["id"], response)
            return content
    except Exception as exc:
        logger.exception("API关键词请求失败: rule_id={}, request={}, response={}", config["id"], request, response)
        if isinstance(exc, ApiKeywordRequestError):
            raise
        if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
            raise ApiKeywordRequestError(f"API关键词请求超时（{timeout}秒），请稍后重试") from exc
        raise ApiKeywordRequestError(f"API关键词请求失败：{exc}") from exc
