"""
闲鱼接口发布的媒体处理服务。

功能：
1. 读取本地、静态目录或远程图片；
2. 使用抓包中的 stream-upload 接口上传图片并返回发布载荷结构；
3. 对媒体接口返回完整日志，便于定位账号、Cookie和平台业务错误。
"""
from __future__ import annotations

import asyncio
import mimetypes
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp
from loguru import logger
from PIL import Image


IMAGE_UPLOAD_URL = (
    "https://stream-upload.goofish.com/api/upload.api"
    "?floderId=0&appkey=fleamarket&_input_charset=utf-8"
)
MEDIA_TIMEOUT = aiohttp.ClientTimeout(total=90)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)
# 阿里图床（img.alicdn.com 等）对不带浏览器请求头的下载会返回 HTTP 420 限流。
# 编辑时回填平台原有规格图必须下载原图才能拿到真实宽高，因此下载也要带浏览器头。
# Accept 刻意不声明 webp/avif：图床会按 Accept 做格式协商，声明后返回的字节格式
# 与 URL 后缀不一致（.png 拿到 webp），上传时容易因扩展名与内容不符出问题。
IMAGE_DOWNLOAD_HEADERS = {
    "Accept": "image/jpeg,image/png,image/*;q=0.8,*/*;q=0.5",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.goofish.com/",
    "User-Agent": BROWSER_USER_AGENT,
}
# 图床限流与瞬时故障的状态码：这些情况重试有意义，其余状态码直接失败
RETRYABLE_DOWNLOAD_STATUS = {420, 429, 500, 502, 503, 504}
# 重试等待秒数，长度即额外重试次数
DOWNLOAD_RETRY_DELAYS = (1.0, 3.0)


class PublishMediaError(RuntimeError):
    """媒体读取、上传或平台响应异常。"""


def _resolve_local_path(value: str, static_root: Path | None) -> Path:
    """解析接口请求中的本地路径，禁止把不存在的路径传给上传接口。"""
    normalized = value.strip()
    if normalized.startswith("/static/") or normalized.startswith("static/"):
        relative = normalized.lstrip("/").replace("static/", "", 1)
        if static_root:
            root = static_root
        else:
            repo_or_backend = Path(__file__).resolve().parents[2]
            root = repo_or_backend / "static" if repo_or_backend.name == "backend-web" else repo_or_backend / "backend-web" / "static"
        return root / relative
    return Path(normalized).expanduser()


def _content_type_for(name: str) -> str:
    """根据文件名推断上传 Content-Type。"""
    guessed = mimetypes.guess_type(name)[0]
    return guessed if guessed and guessed.startswith("image/") else "image/jpeg"


def _dimensions(content: bytes) -> tuple[int, int]:
    """读取图片尺寸，平台载荷需要宽高字段。"""
    try:
        with Image.open(BytesIO(content)) as image:
            return int(image.width), int(image.height)
    except Exception as exc:  # noqa: BLE001
        raise PublishMediaError(f"图片无法解析，不能发布：{exc}") from exc


async def _download_image(url: str) -> tuple[bytes, str]:
    """下载远程图片，带浏览器请求头并对图床限流做有限重试。

    Args:
        url: 图片地址（http/https）。
    Returns:
        tuple: (图片字节, Content-Type)
    Raises:
        PublishMediaError: 下载失败或返回空内容，错误信息为中文，直接展示给用户。
    """
    last_status = 0
    for attempt in range(len(DOWNLOAD_RETRY_DELAYS) + 1):
        async with aiohttp.ClientSession(
            timeout=MEDIA_TIMEOUT,
            cookie_jar=aiohttp.DummyCookieJar(),
        ) as session:
            async with session.get(url, headers=IMAGE_DOWNLOAD_HEADERS) as response:
                content = await response.read()
                last_status = response.status
                if response.status == 200 and content:
                    content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0]
                    return content, content_type.strip()
        if last_status not in RETRYABLE_DOWNLOAD_STATUS or attempt >= len(DOWNLOAD_RETRY_DELAYS):
            break
        logger.warning(
            f"远程图片下载被限流或失败，准备重试: url={url}, http_status={last_status}, "
            f"attempt={attempt + 1}"
        )
        await asyncio.sleep(DOWNLOAD_RETRY_DELAYS[attempt])
    if last_status in RETRYABLE_DOWNLOAD_STATUS:
        raise PublishMediaError(
            f"远程图片下载被图床限流（HTTP {last_status}），已重试仍失败，请稍后重试"
        )
    raise PublishMediaError(f"远程图片下载失败：HTTP {last_status}")


async def _read_image(value: str, static_root: Path | None) -> tuple[bytes, str, str]:
    """读取远程或本地图片内容。"""
    normalized = value.strip()
    if normalized.lower().startswith(("http://", "https://")):
        try:
            content, content_type = await _download_image(normalized)
            name = Path(urlparse(normalized).path).name or "publish-image.jpg"
            # 图床返回的实际格式可能与 URL 后缀不一致，按 Content-Type 校正文件名，
            # 避免上传时扩展名与内容不符
            extension = mimetypes.guess_extension(content_type) if content_type else None
            if extension == ".jpe":
                extension = ".jpg"
            if extension in IMAGE_EXTENSIONS and Path(name).suffix.lower() != extension:
                name = f"{Path(name).stem or 'publish-image'}{extension}"
            return content, name, content_type or _content_type_for(name)
        except PublishMediaError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PublishMediaError(f"远程图片下载失败：{exc}") from exc

    path = _resolve_local_path(normalized, static_root)
    if not path.is_file():
        raise PublishMediaError(f"图片文件不存在：{path}")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise PublishMediaError(f"读取图片失败：{path}，{exc}") from exc
    if not content:
        raise PublishMediaError(f"图片文件为空：{path}")
    return content, path.name, _content_type_for(path.name)


async def upload_publish_image(
    value: str,
    cookie: str,
    *,
    static_root: str | Path | None = None,
) -> dict[str, Any]:
    """上传一张图片并返回闲鱼 imageInfoDOList 元素。"""
    root = Path(static_root) if static_root else None
    content, name, content_type = await _read_image(value, root)
    return await upload_publish_image_content(
        content,
        name,
        cookie,
        content_type=content_type,
        source=value,
    )


async def upload_publish_image_content(
    content: bytes,
    name: str,
    cookie: str,
    *,
    content_type: str | None = None,
    source: str = "内存图片",
) -> dict[str, Any]:
    """上传内存中的图片字节，用于视频封面等派生媒体。"""
    if not content:
        raise PublishMediaError("图片文件为空")
    content_type = content_type or _content_type_for(name)
    width, height = _dimensions(content)
    suffix = Path(name).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        suffix = ".jpg"
    filename = f"publish_api_{uuid.uuid4().hex}{suffix}"
    form = aiohttp.FormData()
    form.add_field("file", content, filename=filename, content_type=content_type)
    headers = {
        "Accept": "*/*",
        "Cookie": cookie,
        "Origin": "https://seller.goofish.com",
        "Referer": "https://seller.goofish.com/?site=COMMONPRO",
        "User-Agent": BROWSER_USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        async with aiohttp.ClientSession(
            timeout=MEDIA_TIMEOUT,
            cookie_jar=aiohttp.DummyCookieJar(),
        ) as session:
            async with session.post(IMAGE_UPLOAD_URL, data=form, headers=headers) as response:
                response_text = await response.text()
                logger.info(
                    f"闲鱼图片上传完整返回: source={source}, "
                    f"http_status={response.status}, response={response_text}"
                )
                if response.status != 200:
                    raise PublishMediaError(f"闲鱼图片上传失败：HTTP {response.status}")
                try:
                    body = await response.json(content_type=None)
                except ValueError as exc:
                    raise PublishMediaError("闲鱼图片上传返回不是有效JSON") from exc
    except PublishMediaError:
        raise
    except (aiohttp.ClientError, OSError, TimeoutError) as exc:
        raise PublishMediaError(f"闲鱼图片上传请求失败：{exc}") from exc

    uploaded = body.get("object") if isinstance(body, dict) else None
    if not isinstance(uploaded, dict) or not uploaded.get("url") or body.get("success") is not True:
        raise PublishMediaError("闲鱼图片上传失败：接口未返回有效图片地址")
    pix = str(uploaded.get("pix") or f"{width}x{height}")
    try:
        pix_width, pix_height = (int(part) for part in pix.lower().split("x", 1))
    except (TypeError, ValueError):
        pix_width, pix_height = width, height
    return {
        "extraInfo": {"isH": "false", "isT": "false", "raw": "false"},
        "isQrCode": False,
        "url": str(uploaded["url"]),
        "heightSize": pix_height,
        "widthSize": pix_width,
        "major": False,
        "type": 0,
        "status": "done",
    }


__all__ = ["PublishMediaError", "upload_publish_image", "upload_publish_image_content"]
