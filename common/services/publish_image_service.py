"""
公共发布图片服务

功能：
1. 下载远程图片到临时目录
2. 清理发布流程产生的临时图片
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import aiohttp
from loguru import logger

_REMOTE_IMAGE_TIMEOUT = aiohttp.ClientTimeout(total=60)
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


async def download_remote_image(url: str) -> str:
    """下载远程图片到公共临时目录并返回本地路径。"""
    async with aiohttp.ClientSession(timeout=_REMOTE_IMAGE_TIMEOUT) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            content = await response.read()
            if not content:
                raise ValueError("远程图片内容为空")
            content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()

    suffix = _guess_image_suffix(url, content_type)
    file_path = _ensure_temp_upload_dir() / f"publish_remote_{uuid4().hex}{suffix}"
    file_path.write_bytes(content)
    logger.info(f"远程图片下载成功: {url} -> {file_path}")
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
