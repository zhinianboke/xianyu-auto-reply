"""群二维码文件的读写与静态响应，兼容已有图片地址。"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from os.path import normcase
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi.staticfiles import StaticFiles
from PIL import Image
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response
from starlette.types import Scope

from app.core.config import get_settings
from common.utils.local_image_upload import ImageUploadError, sniff_image_ext

STATIC_ROOT = Path(get_settings().static_dir).resolve()
QRCODE_DIR = STATIC_ROOT / "qrcode"
QRCODE_TYPES = ("wechat", "qq", "wechat_official", "telegram", "reward")
MAX_QRCODE_BYTES = 2 * 1024 * 1024
NO_STORE = {"Cache-Control": "no-store"}
_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".gif": "GIF", ".webp": "WEBP", ".bmp": "BMP"}
_MEDIA_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}
_STEMS = {kind: f"{kind.replace('_', '-')}-group" for kind in QRCODE_TYPES}
_ALIASES = {f"{stem}{ext}": kind for kind, stem in _STEMS.items() for ext in _MEDIA_TYPES}


@dataclass(frozen=True)
class QrcodeImage:
    """一次读取或上传的二维码快照，包含图片内容及其公开后缀。"""

    content: bytes
    extension: str

    def url(self, kind: str) -> str:
        """返回带内容版本的本站图片地址，参数为已校验的二维码类型。"""
        revision = sha256(self.content).hexdigest()[:24]
        return f"/static/qrcode/{_STEMS[kind]}{self.extension}?v={revision}"


def _current_path(kind: str) -> Path:
    """返回该类型的新图片位置，独立于上传格式。"""
    return QRCODE_DIR / ".current" / _STEMS[kind]


def _validate_image(content: bytes) -> str:
    """校验上传字节和可解码的图像，返回实际图片后缀。"""
    extension = sniff_image_ext(content)
    if extension is None:
        raise ImageUploadError("请上传有效的 PNG、JPEG、GIF、WEBP 或 BMP 图片")

    formats = [_FORMATS[extension]]
    try:
        with Image.open(BytesIO(content), formats=formats) as image:
            if Image.MAX_IMAGE_PIXELS is not None and image.width * image.height > Image.MAX_IMAGE_PIXELS:
                raise Image.DecompressionBombError("二维码图片像素过多")
            image.verify()
        # verify() 不会完整解码像素，截断的 JPEG 也可能通过该检查。
        with Image.open(BytesIO(content), formats=formats) as image:
            image.load()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ImageUploadError("二维码图片损坏或尺寸过大") from exc
    return extension


def read_qrcode(kind: str, legacy_extension: str | None = None) -> QrcodeImage | None:
    """读取当前图片。没有换过图时，直链读取原文件，地址接口按原顺序查找。"""
    try:
        content = _current_path(kind).read_bytes()
    except FileNotFoundError:
        extensions = (legacy_extension,) if legacy_extension else _MEDIA_TYPES
        for extension in extensions:
            try:
                content = (QRCODE_DIR / f"{_STEMS[kind]}{extension}").read_bytes()
            except FileNotFoundError:
                continue
            return QrcodeImage(content, extension)
        return None
    extension = sniff_image_ext(content)
    if extension is None:
        raise ValueError("已保存的二维码格式无法识别")
    return QrcodeImage(content, extension)


def save_qrcode(kind: str, content: bytes) -> QrcodeImage:
    """校验并原子替换指定类型的二维码，写入失败时保留上一张图片。"""
    extension = _validate_image(content)
    target = _current_path(kind)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with NamedTemporaryFile(dir=target.parent, delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
        temp_path.replace(target)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return QrcodeImage(content, extension)


class QrcodeStaticFiles(StaticFiles):
    """固定的群二维码链接始终读取当前图片，其他静态文件沿用原处理。"""

    async def get_response(self, path: str, scope: Scope) -> Response:
        """使用 Starlette 归一化后的路径处理二维码链接，其他文件沿用原响应。"""
        parts = Path(normcase(path)).parts
        if parts[:2] == ("qrcode", ".current"):
            return Response(status_code=404, headers=NO_STORE)
        kind = _ALIASES.get(parts[1]) if len(parts) == 2 and parts[0] == "qrcode" else None
        if kind is None or scope["method"] not in ("GET", "HEAD"):
            return await super().get_response(path, scope)
        image = await run_in_threadpool(read_qrcode, kind, Path(parts[1]).suffix)
        if image is None:
            return Response(status_code=404, headers=NO_STORE)
        return Response(
            image.content if scope["method"] == "GET" else b"",
            media_type=_MEDIA_TYPES[sniff_image_ext(image.content) or image.extension],
            headers={**NO_STORE, "Content-Length": str(len(image.content)), "X-Content-Type-Options": "nosniff"},
        )
