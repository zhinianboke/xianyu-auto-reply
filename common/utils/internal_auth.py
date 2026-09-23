"""
服务间内部 API 鉴权工具。

功能：
1. 统一定义内部 API 请求头名称。
2. 为 backend-web、scheduler 和其他内部调用方生成鉴权请求头。
3. 使用常量时间比较，避免令牌比较引入时序侧信道。
"""
from __future__ import annotations

from hmac import compare_digest
from typing import Mapping
from urllib.parse import urlparse

from fastapi import HTTPException, status

INTERNAL_AUTH_HEADER = "X-Internal-Token"
MIN_INTERNAL_TOKEN_LENGTH = 32


def build_internal_auth_headers(token: str | None) -> dict[str, str]:
    """根据服务间令牌生成请求头；未配置令牌时抛出明确异常。"""
    normalized = (token or "").strip()
    if len(normalized) < MIN_INTERNAL_TOKEN_LENGTH:
        raise RuntimeError("INTERNAL_API_TOKEN 未配置或长度不足32位，无法调用内部 API")
    return {INTERNAL_AUTH_HEADER: normalized}


def is_valid_internal_token(provided: str | None, expected: str | None) -> bool:
    """校验请求令牌是否与服务配置一致。"""
    configured = (expected or "").strip()
    presented = (provided or "").strip()
    return bool(
        len(configured) >= MIN_INTERNAL_TOKEN_LENGTH
        and len(presented) >= MIN_INTERNAL_TOKEN_LENGTH
        and compare_digest(presented, configured)
    )


def require_valid_internal_token(provided: str | None, expected: str | None) -> None:
    """校验服务间令牌；失败时抛出统一的 401 业务异常。"""
    if not is_valid_internal_token(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="内部 API 鉴权失败",
            headers={"WWW-Authenticate": INTERNAL_AUTH_HEADER},
        )


def merge_internal_auth_headers(
    headers: Mapping[str, str] | None,
    token: str | None,
) -> dict[str, str]:
    """在保留调用方请求头的基础上加入内部 API 鉴权头。"""
    # HTTP 头名称大小写不敏感：先移除调用方可能传入的旧值，避免
    # ``x-internal-token`` 与规范大小写的头同时存在而由客户端随机选值。
    merged = {
        key: value
        for key, value in (headers or {}).items()
        if key.lower() != INTERNAL_AUTH_HEADER.lower()
    }
    merged.update(build_internal_auth_headers(token))
    return merged


def is_internal_api_path(path: str | None) -> bool:
    """判断 URL 路径是否严格属于 /internal API 命名空间。"""
    normalized = (path or "").split("?", 1)[0].rstrip("/")
    return normalized == "/internal" or normalized.startswith("/internal/")


def is_internal_api_url(
    url: str | None,
    allowed_base_urls: tuple[str, ...] = (),
) -> bool:
    """判断 URL 是否指向受信任服务的严格 /internal API 路径。

    绝对 URL 必须与调用方配置的内部服务 origin 匹配；相对 URL 仅按路径判断。
    """
    parsed = urlparse(url or "")
    if not is_internal_api_path(parsed.path):
        return False
    if not parsed.netloc:
        return True
    if not allowed_base_urls:
        return False
    target_origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    for base_url in allowed_base_urls:
        base = urlparse((base_url or "").strip())
        if base.scheme and base.netloc:
            base_origin = f"{base.scheme.lower()}://{base.netloc.lower()}"
            if target_origin == base_origin:
                return True
    return False
