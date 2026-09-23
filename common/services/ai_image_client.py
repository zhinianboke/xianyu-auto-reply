"""
AI 图片生成通用客户端

功能：
1. 调用 OpenAI 兼容的 /images/generations 生成图片（支持返回 url 或 b64_json 两种形态）
2. 对第三方返回的图片地址做安全校验，拒绝内网/回环/链路本地地址（防 SSRF）
3. 下载/解码后复用公共图片落盘工具写入静态目录，返回可直接入库的相对 URL

说明：
- 图片来源是第三方响应，属于不可信输入：协议、目标 IP、字节大小、真实格式都必须校验。
- 落盘统一走 common.utils.local_image_upload.save_image_bytes，与用户上传图片同一套
  扩展名白名单与大小上限，不另开后门。
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
from pathlib import Path
from typing import Any, NamedTuple, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

from common.services.ai_provider_service import build_openai_url
from common.services.ai_text_client import AiCallError, request_json_with_retries
from common.utils.local_image_upload import DEFAULT_MAX_SIZE, save_image_bytes

# 默认请求超时（秒）：图片生成普遍比文案慢
DEFAULT_IMAGE_TIMEOUT = 180.0

# 单张图片最大字节数，与用户上传图片保持一致
IMAGE_MAX_SIZE = DEFAULT_MAX_SIZE

# 单条素材最多生成图片数量，与素材库 images 字段上限一致
MAX_IMAGE_COUNT = 9

# 素材图片对外访问前缀（与 /product-publish/upload/images 保持一致）
IMAGE_URL_PREFIX = "/static/uploads/products"


class SavedImage(NamedTuple):
    """已落盘的图片

    Attributes:
        url: 可入库、可被前端预览的相对地址。
        filepath: 本地绝对路径，供调用方在业务失败时清理。
    """

    url: str
    filepath: Path


async def _ensure_public_http_url(url: str) -> None:
    """校验图片地址可安全下载：必须是 http/https 且指向公网地址

    第三方接口返回的地址不可信，若直接 GET 就等于把服务器当跳板去访问内网
    （数据库、管理后台、云元数据接口 169.254.169.254 等），因此这里解析域名
    拿到真实 IP 后逐个判断，命中内网/回环/链路本地/保留地址一律拒绝。

    Args:
        url: 待校验的图片地址。
    Raises:
        AiCallError: 协议不合法、域名解析失败或目标地址不是公网地址。
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise AiCallError(f"图片地址协议不受支持：{parsed.scheme or '空'}")
    if not parsed.hostname:
        raise AiCallError("图片地址缺少主机名")

    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, None)
    except OSError as exc:
        raise AiCallError(f"图片地址解析失败：{exc}") from exc

    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise AiCallError(f"图片地址解析结果非法：{address}")
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise AiCallError("图片地址指向内网或保留地址，已拒绝下载")


async def _download_image(
    client: httpx.AsyncClient,
    url: str,
    timeout: float,
    max_size: int = IMAGE_MAX_SIZE,
) -> bytes:
    """流式下载图片并限制总字节数

    先看 Content-Length 快速拒绝，再边收边累计实际字节，超限立即中断，
    避免第三方返回超大文件把内存/磁盘打满。

    Args:
        client: httpx 异步客户端。
        url: 已通过安全校验的图片地址。
        timeout: 超时秒数。
        max_size: 最大字节数。
    Returns:
        图片字节内容。
    Raises:
        AiCallError: 下载失败或超过大小上限。
    """
    await _ensure_public_http_url(url)

    size_text = f"{max_size / (1024 * 1024):.0f}MB"
    try:
        async with client.stream("GET", url, timeout=timeout) as response:
            # 不跟随重定向：3xx 的响应体不是图片，且跳转目标未经过 SSRF 校验
            if response.status_code >= 300:
                raise AiCallError(f"下载图片失败：HTTP {response.status_code}")

            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > max_size:
                raise AiCallError(f"图片大小超过{size_text}，已跳过")

            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_size:
                    raise AiCallError(f"图片大小超过{size_text}，已跳过")
                chunks.append(chunk)
    except httpx.TimeoutException as exc:
        raise AiCallError("下载图片超时", retryable=True) from exc
    except httpx.HTTPError as exc:
        raise AiCallError(f"下载图片失败：{exc}", retryable=True) from exc

    return b"".join(chunks)


def _extract_image_payloads(data: dict[str, Any]) -> list[dict[str, Any]]:
    """从响应体中取出图片条目列表

    Args:
        data: /images/generations 响应体。
    Returns:
        图片条目列表，每项可能含 url 或 b64_json。
    Raises:
        AiCallError: 响应里没有任何图片条目。
    """
    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise AiCallError("图片接口未返回任何图片")
    return [item for item in items if isinstance(item, dict)]


async def _resolve_image_bytes(
    client: httpx.AsyncClient,
    item: dict[str, Any],
    timeout: float,
) -> bytes:
    """把单个图片条目还原成字节内容

    Args:
        client: httpx 异步客户端。
        item: 图片条目（含 url 或 b64_json）。
        timeout: 下载超时秒数。
    Returns:
        图片字节内容。
    Raises:
        AiCallError: 条目里既没有 url 也没有可解码的 b64_json。
    """
    b64_content = item.get("b64_json")
    if b64_content:
        try:
            return base64.b64decode(str(b64_content), validate=True)
        except Exception as exc:
            raise AiCallError("图片接口返回的base64内容无法解码") from exc

    url = str(item.get("url") or "").strip()
    if url:
        return await _download_image(client, url, timeout)

    raise AiCallError("图片接口返回的条目既没有url也没有b64_json")


async def generate_images(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    size: str,
    count: int,
    upload_dir: Path,
    filename_prefix: str = "ai",
    timeout: float = DEFAULT_IMAGE_TIMEOUT,
    client: Optional[httpx.AsyncClient] = None,
) -> list[SavedImage]:
    """调用图片生成接口并把结果落盘

    Args:
        base_url: 图片接口基础地址。
        api_key: 接口密钥，仅用于 Authorization 头。
        model: 图片模型名称。
        prompt: 图片提示词。
        size: 图片尺寸，如 1024x1024。
        count: 期望生成张数（会被压到 1~9）。
        upload_dir: 落盘目录（一般是 get_upload_path("products")）。
        filename_prefix: 文件名前缀。
        timeout: 单次请求超时（秒）。
        client: 复用的 httpx 客户端；为 None 时内部自建并在结束后关闭。

    Returns:
        已成功落盘的图片列表；部分图片失败时返回成功的那部分。

    Raises:
        AiCallError: 接口调用失败，或所有图片都无法落盘。
    """
    safe_count = max(1, min(int(count or 1), MAX_IMAGE_COUNT))
    url = build_openai_url(base_url, "/images/generations")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "prompt": prompt, "size": size, "n": safe_count}

    logger.info(
        f"【AI铺货】调用图片接口 model={model} size={size} n={safe_count} api_key长度={len(api_key or '')}"
    )

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout)
    saved: list[SavedImage] = []
    try:
        data = await request_json_with_retries(
            http_client, url, headers, payload, timeout, label="图片接口"
        )
        items = _extract_image_payloads(data)

        last_error: Optional[str] = None
        for item in items[:safe_count]:
            try:
                content = await _resolve_image_bytes(http_client, item, timeout)
                filepath, filename = await save_image_bytes(
                    content, upload_dir, filename_prefix=filename_prefix, short_uuid=True
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # 单张失败（含磁盘写入失败）只跳过这一张，不影响已成功的图片
                last_error = getattr(exc, "message", str(exc))
                logger.warning(f"【AI铺货】单张图片处理失败，已跳过：{last_error}")
                continue
            saved.append(SavedImage(url=f"{IMAGE_URL_PREFIX}/{filename}", filepath=filepath))

        if not saved:
            raise AiCallError(f"图片生成失败：{last_error or '没有可用的图片'}")
        return saved
    except BaseException:
        # 整体失败时清理已落盘的图片，避免孤儿文件
        cleanup_saved_images(saved)
        raise
    finally:
        if owns_client:
            await http_client.aclose()


def cleanup_saved_images(images: list[SavedImage]) -> None:
    """删除已落盘的图片（素材入库失败时调用，避免留下孤儿文件）

    Args:
        images: 待清理的图片列表。
    """
    for image in images:
        try:
            image.filepath.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(f"【AI铺货】清理图片失败 path={image.filepath} error={exc}")


__all__ = [
    "DEFAULT_IMAGE_TIMEOUT",
    "IMAGE_URL_PREFIX",
    "MAX_IMAGE_COUNT",
    "SavedImage",
    "cleanup_saved_images",
    "generate_images",
]


