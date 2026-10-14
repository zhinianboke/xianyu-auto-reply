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

# ---------------------------------------------------------------------------
# [代理支持补丁 2026-09-20] 媒体上传/下载按账号代理走代理。
# 背景：服务器在境外时直连闲鱼图床（stream-upload.goofish.com）上传会被限速，
# 导致发布图片 90 秒超时（"闲鱼图片上传请求失败"）。此处支持 socks5/socks4/http
# 代理；无代理配置或依赖缺失时保持原有直连行为。
# ---------------------------------------------------------------------------

_PROXY_TYPE_MAP = {
    "socks5": "SOCKS5",
    "socks4": "SOCKS4",
    "http": "HTTP",
    "https": "HTTP",
}


def resolve_account_proxy(account_id: str | None) -> dict[str, Any] | None:
    """读取账号代理配置；无代理或读取失败时返回 None（回退直连）。"""
    if not account_id:
        return None
    try:
        from common.db.compat import db_manager

        config = db_manager.get_cookie_proxy_config(account_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"媒体上传读取账号代理配置失败，将直连: account_id={account_id}, error={exc}")
        return None
    if not config:
        return None
    if str(config.get("proxy_type") or "none").lower() in ("", "none"):
        return None
    if not config.get("proxy_host") or not config.get("proxy_port"):
        return None
    return config


def build_proxy_connector(proxy: dict[str, Any] | None):
    """按代理配置构建 aiohttp 连接器；无代理/依赖缺失/配置异常时返回 None。"""
    if not proxy:
        return None
    proxy_type = str(proxy.get("proxy_type") or "").lower()
    mapped = _PROXY_TYPE_MAP.get(proxy_type)
    host = str(proxy.get("proxy_host") or "").strip()
    try:
        port = int(proxy.get("proxy_port") or 0)
    except (TypeError, ValueError):
        port = 0
    if mapped is None or not host or port <= 0:
        return None
    try:
        from aiohttp_socks import ProxyConnector, ProxyType
    except ImportError:
        # 兼容挂载式补丁部署：依赖库位于 /app/patch_libs
        import sys

        if "/app/patch_libs" not in sys.path:
            sys.path.insert(0, "/app/patch_libs")
        try:
            from aiohttp_socks import ProxyConnector, ProxyType
        except ImportError:
            logger.error("aiohttp_socks 不可用，媒体上传无法走代理，回退直连")
            return None
    try:
        connector = ProxyConnector(
            proxy_type=getattr(ProxyType, mapped),
            host=host,
            port=port,
            username=proxy.get("proxy_user") or None,
            password=proxy.get("proxy_pass") or None,
            rdns=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"构建代理连接器失败，媒体上传回退直连: {exc}")
        return None
    logger.info(f"媒体上传启用账号代理: {proxy_type}://{host}:{port}")
    return connector


async def close_proxy_connector(connector) -> None:
    """关闭本次调用自建的连接器；None 时安全跳过。"""
    if connector is None:
        return
    try:
        await connector.close()
    except Exception:  # noqa: BLE001
        pass


class PublishMediaError(RuntimeError):
    """媒体读取、上传或平台响应异常。"""


def _resolve_local_path(value: str, static_root: Path | str | None) -> Path:
    """解析接口请求中的本地路径，禁止把不存在的路径传给上传接口。"""
    normalized = value.strip().replace("\\", "/")  # 统一路径分隔符为正斜杠
    if normalized.startswith("/static/") or normalized.startswith("static/"):
        relative = normalized.lstrip("/").replace("static/", "", 1)
        # 仅信任“绝对路径”的 static_root（Docker 共享卷）。相对值（如各服务 .env 里的
        # "static"）会因每个服务工作目录不同而指向各自目录：scheduler 续售发布时会落到
        # scheduler/static，读不到 backend-web 上传的图片。相对值一律忽略，统一回退到项目内
        # backend-web/static 共享目录，与人脸验证截图保持同一份存储。
        if static_root and Path(static_root).is_absolute():
            root = Path(static_root)
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


COMPRESS_THRESHOLD_BYTES = 600 * 1024
COMPRESS_MAX_DIMENSION = 1920
COMPRESS_QUALITY = 85
UPLOAD_MAX_ATTEMPTS = 3


def _maybe_compress_image(content: bytes, name: str) -> tuple[bytes, str]:
    """大图先压缩再上传，降低代理链路传输量（策略对齐聊天图片上传）。

    代理带宽有限（实测 ~15-55KB/s），1-2MB 的原图会触发 90 秒上传超时；
    超过阈值的非 GIF 图片转为 JPEG（最长边 1920、质量 85），通常可压到 1/5 以下。
    压缩失败或未变小则按原图上传。
    """
    if len(content) <= COMPRESS_THRESHOLD_BYTES:
        return content, name
    if Path(name).suffix.lower() == ".gif":
        return content, name
    try:
        with Image.open(BytesIO(content)) as img:
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            width, height = img.size
            if width > COMPRESS_MAX_DIMENSION or height > COMPRESS_MAX_DIMENSION:
                if width > height:
                    new_width = COMPRESS_MAX_DIMENSION
                    new_height = max(1, int(height * COMPRESS_MAX_DIMENSION / width))
                else:
                    new_height = COMPRESS_MAX_DIMENSION
                    new_width = max(1, int(width * COMPRESS_MAX_DIMENSION / height))
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            img.save(buffer, "JPEG", quality=COMPRESS_QUALITY, optimize=True)
            compressed = buffer.getvalue()
            if len(compressed) > 800 * 1024:
                buffer = BytesIO()
                img.save(buffer, "JPEG", quality=70, optimize=True)
                compressed = buffer.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"图片压缩失败，按原图上传: {exc}")
        return content, name
    if len(compressed) >= len(content):
        return content, name
    new_name = f"{Path(name).stem or 'publish-image'}.jpg"
    logger.info(f"图片压缩完成: {len(content) / 1024:.0f}KB -> {len(compressed) / 1024:.0f}KB")
    return compressed, new_name


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
    account_id: str | None = None,
    proxy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """上传一张图片并返回闲鱼 imageInfoDOList 元素（可按账号代理）。"""
    resolved_proxy = proxy if proxy is not None else resolve_account_proxy(account_id)
    root = Path(static_root) if static_root else None
    content, name, content_type = await _read_image(value, root)
    content, name = _maybe_compress_image(content, name)
    if name.lower().endswith((".jpg", ".jpeg")):
        content_type = "image/jpeg"
    return await upload_publish_image_content(
        content,
        name,
        cookie,
        content_type=content_type,
        source=value,
        proxy=resolved_proxy,
    )


async def upload_publish_image_content(
    content: bytes,
    name: str,
    cookie: str,
    *,
    content_type: str | None = None,
    source: str = "内存图片",
    account_id: str | None = None,
    proxy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """上传内存中的图片字节，用于视频封面等派生媒体。"""
    if not content:
        raise PublishMediaError("图片文件为空")
    content, name = _maybe_compress_image(content, name)
    if name.lower().endswith((".jpg", ".jpeg")):
        content_type = "image/jpeg"
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
    resolved_proxy = proxy if proxy is not None else resolve_account_proxy(account_id)
    body: Any = None
    last_error: Exception | None = None
    for attempt in range(1, UPLOAD_MAX_ATTEMPTS + 1):
        connector = build_proxy_connector(resolved_proxy)
        try:
            session_kwargs: dict[str, Any] = {
                "timeout": MEDIA_TIMEOUT,
                "cookie_jar": aiohttp.DummyCookieJar(),
            }
            if connector is not None:
                session_kwargs["connector"] = connector
            async with aiohttp.ClientSession(**session_kwargs) as session:
                async with session.post(IMAGE_UPLOAD_URL, data=form, headers=headers) as response:
                    response_text = await response.text()
                    logger.info(
                        f"闲鱼图片上传完整返回: source={source}, attempt={attempt}, "
                        f"http_status={response.status}, response={response_text}"
                    )
                    if response.status != 200:
                        raise PublishMediaError(f"闲鱼图片上传失败：HTTP {response.status}")
                    try:
                        body = await response.json(content_type=None)
                    except ValueError as exc:
                        raise PublishMediaError("闲鱼图片上传返回不是有效JSON") from exc
            break
        except PublishMediaError:
            raise
        except (aiohttp.ClientError, OSError, TimeoutError) as exc:
            last_error = exc
            if attempt < UPLOAD_MAX_ATTEMPTS:
                logger.warning(
                    f"闲鱼图片上传连接异常（第 {attempt}/{UPLOAD_MAX_ATTEMPTS} 次），准备重试: {exc}"
                )
                await asyncio.sleep(1.0)
        finally:
            await close_proxy_connector(connector)
    else:
        raise PublishMediaError(f"闲鱼图片上传请求失败：{last_error}") from last_error

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


__all__ = [
    "PublishMediaError",
    "upload_publish_image",
    "upload_publish_image_content",
    "resolve_account_proxy",
    "build_proxy_connector",
    "close_proxy_connector",
]
