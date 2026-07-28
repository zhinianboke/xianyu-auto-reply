"""
公共发布图片服务

功能：
1. 下载远程图片到临时目录
2. 清理发布流程产生的临时图片
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import aiohttp
from loguru import logger

_REMOTE_IMAGE_TIMEOUT = aiohttp.ClientTimeout(total=60)
_MAX_REMOTE_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_REDIRECTS = 3
_TEMP_UPLOAD_DIR = Path(tempfile.gettempdir()) / "xianyu_publish_images"
_CONTENT_TYPE_SUFFIX_MAP = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}


def _ensure_temp_upload_dir() -> Path:
    """确保公共发布临时图片目录存在。"""
    _TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return _TEMP_UPLOAD_DIR


def _guess_image_suffix(url: str, content_type: str) -> str:
    """根据 URL 和响应类型推断图片后缀。"""
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return _CONTENT_TYPE_SUFFIX_MAP.get(content_type.lower(), ".jpg")


async def _validate_public_image_url(url: str) -> None:
    """拒绝非 HTTP(S)、内网、回环和链路本地目标。"""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("远程图片必须是有效的 HTTP/HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("远程图片 URL 不允许携带用户凭据")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = await asyncio.get_running_loop().getaddrinfo(
        parsed.hostname,
        port,
        type=socket.SOCK_STREAM,
    )
    if not addresses:
        raise ValueError("远程图片域名无法解析")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("远程图片地址不允许指向内网或本机")


async def download_remote_image(url: str) -> str:
    """下载远程图片到公共临时目录并返回本地路径。"""
    async with aiohttp.ClientSession(timeout=_REMOTE_IMAGE_TIMEOUT) as session:
        current_url = url
        for redirect_count in range(_MAX_REDIRECTS + 1):
            await _validate_public_image_url(current_url)
            async with session.get(current_url, allow_redirects=False) as response:
                if 300 <= response.status < 400:
                    if redirect_count >= _MAX_REDIRECTS:
                        raise ValueError("远程图片重定向次数过多")
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("远程图片重定向缺少目标地址")
                    current_url = urljoin(current_url, location)
                    continue

                response.raise_for_status()
                content_type = (
                    response.headers.get("Content-Type") or ""
                ).split(";", 1)[0].strip().lower()
                if content_type not in _CONTENT_TYPE_SUFFIX_MAP:
                    raise ValueError(f"远程资源不是受支持的图片类型: {content_type or 'unknown'}")
                if response.content_length and response.content_length > _MAX_REMOTE_IMAGE_BYTES:
                    raise ValueError("远程图片超过 10MB 限制")

                chunks: list[bytes] = []
                total_bytes = 0
                async for chunk in response.content.iter_chunked(64 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > _MAX_REMOTE_IMAGE_BYTES:
                        raise ValueError("远程图片超过 10MB 限制")
                    chunks.append(chunk)
                content = b"".join(chunks)
                if not content:
                    raise ValueError("远程图片内容为空")
                break
        else:
            raise ValueError("远程图片下载失败")

    suffix = _guess_image_suffix(current_url, content_type)
    file_path = _ensure_temp_upload_dir() / f"publish_remote_{uuid4().hex}{suffix}"
    file_path.write_bytes(content)
    logger.info(f"远程图片下载成功: {urlparse(current_url).hostname} -> {file_path}")
    return str(file_path)


def cleanup_temp_images(file_paths: list[str]) -> None:
    """清理发布流程产生的临时图片文件。"""
    for file_path in file_paths:
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                logger.info(f"已清理临时图片: {path}")
        except Exception as exc:
            logger.warning(f"清理临时图片失败: {file_path}, {exc}")
